#!/usr/bin/env python
#
# Tool to generate reports off feedback data
#
import sys
import os
import psycopg2
import urllib2
import base64
from pygooglechart import PieChart3D
from django.template import Context
from django.template.loader import get_template
from django.conf import settings

measurement_types = (
  ('topic_importance', 'Topic importance'),
  ('content_quality', 'Content quality'),
  ('speaker_knowledge', 'Speaker knowledge'),
  ('speaker_quality', 'Speaker quality'),
)

class SessionStats:
	def __init__(self, db, confid, confname, row):
		self.db = db
		self.confid = confid
		self.confname = confname
		self.row = row
		self.curs = db.cursor()
		if not os.path.exists(self.confname):
			os.mkdir(self.confname)

	def generate(self):
		ratings = []
		comments = []
		for measurement, measurementname in measurement_types:
			q = "SELECT " + measurement + " FROM confreg_conferencesessionfeedback WHERE conference_id=%(confid)s AND session_id=%(sessid)s"
			self.curs.execute(q,{
				'confid': self.confid,
				'sessid': self.row[0],
			})
			n = [0,0,0,0,0]
			count = 0
			for r in self.curs.fetchall():
				n[r[0]-1] = n[r[0]-1] + 1
				count += 1
			ratings.append({
				'title': measurementname,
				'image': self.generate_graph(measurementname, n),
				'values': zip(range(1,6), n),
			})
		self.curs.execute("SELECT speaker_feedback FROM confreg_conferencesessionfeedback WHERE conference_id=%(confid)s AND session_id=%(sessid)s AND NOT speaker_feedback=''", {
			'confid': self.confid,
			'sessid': self.row[0],
		})
		for comment in self.curs.fetchall():
			comments.append(comment[0])

		tmpl = get_template('session_feedback.html')
		f = open("%s/%s.html" % (self.confname, self.row[1]), "w")
		f.write(tmpl.render(Context({
			'ratings': ratings,
			'comments': comments,
			'count': count,
			'session': {
				'name': self.row[1],
				'speaker': self.row[2],
			},
		})).encode('utf-8'))
		f.close()

	def generate_graph(self, measurement, n):
		s = sum(n)
		if s == 0:
			return 0
		chart = PieChart3D(400,200)
		chart.set_title(measurement)
		chart.add_data(n)
		chart.set_pie_labels(["%s (%s%%)" % (v, n[v-1]*100/s) for v in range (1,6)]) #("1","2","3","4","5"))

		opener = urllib2.urlopen(chart.get_url())
		if opener.headers['content-type'] != 'image/png':
			raise BadContentTypeException('Server responded with a ' \
				'content-type of %s' % opener.headers['content-type'])

		return base64.b64encode(opener.read())

def Usage():
	print "Usage: generate_feedback.py <connectionstring> <conferenceshortname>"
	sys.exit(1)

if __name__ == "__main__":
	if len(sys.argv) != 3:
		Usage()
	connstr = sys.argv[1]
	confname = sys.argv[2]

	settings.configure(
		TEMPLATE_DIRS=('template',),
	)
	db = psycopg2.connect(connstr)
	curs = db.cursor()
	curs.execute("SELECT id FROM confreg_conference WHERE urlname=%(url)s", {'url': confname})
	try:
		confid = curs.fetchall()[0][0]
	except:
		print "Could not find conference in database!"
		sys.exit(1)

	curs.execute("""SELECT s.id, title, first_name FROM confreg_conferencesession s
INNER JOIN auth_user ON auth_user.id=s.speaker_id
WHERE conference_id=%(conf)s ORDER BY id
""", {'conf': confid})
	while True:
		row = curs.fetchone()
		if not row: break
		ss = SessionStats(db, confid, confname, row)
		ss.generate()

