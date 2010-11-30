#!/usr/bin/env python
#
# Tool to generate reports off feedback data
#
import sys
import os
import psycopg2
import psycopg2.extensions
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

def generate_pie_graph(measurement, n, labels=None):
	s = sum(n)
	if s == 0:
		return 0
	chart = PieChart3D(400,200)
	chart.set_title(measurement)
	chart.add_data(n)
	if not labels:
		# 1,2,3,4,5 and with the percentage
		labels = ["%s (%s%%)" % (v, n[v-1]*100/s) for v in range (1,6)]
	else:
		# We have text labels, assume same order as values
		labels = ["%s (%s%%)" % (labels[v-1], n[v-1]*100/s) for v in range(1,len(labels)+1)]
	print "Labels: %s" % labels
	chart.set_pie_labels(labels)

	opener = urllib2.urlopen(chart.get_url())
	if opener.headers['content-type'] != 'image/png':
		raise BadContentTypeException('Server responded with a ' \
			  'content-type of %s' % opener.headers['content-type'])

	return base64.b64encode(opener.read())

class SessionStats:
	def __init__(self, db, confid, confname, row):
		self.db = db
		self.confid = confid
		self.confname = confname
		self.row = row
		self.ratings = None
		self.curs = db.cursor()
		if not os.path.exists(self.confname):
			os.mkdir(self.confname)

	def calculate(self):
		self.ratings = []
		for measurement, measurementname in measurement_types:
			q = "SELECT " + measurement + " FROM confreg_conferencesessionfeedback WHERE conference_id=%(confid)s"
			if self.row:
			   q = q + " AND session_id=%(sessid)s"
			self.curs.execute(q,{
				'confid': self.confid,
				'sessid': self.row and self.row[0] or None,
			})
			n = [0,0,0,0,0]
			count = 0
			for r in self.curs.fetchall():
				n[r[0]-1] = n[r[0]-1] + 1
				count += 1
			self.ratings.append({
				'title': measurementname,
				'image': generate_pie_graph(measurementname, n),
				'values': zip(range(1,6), n),
			})
		return count # return the *last* value only. Normally, they're all the same...

	def generate(self):
		count = self.calculate()
		comments = []
		self.curs.execute("SELECT speaker_feedback FROM confreg_conferencesessionfeedback WHERE conference_id=%(confid)s AND session_id=%(sessid)s AND NOT speaker_feedback=''", {
			'confid': self.confid,
			'sessid': self.row[0],
		})
		for comment in self.curs.fetchall():
			comments.append(comment[0])

		tmpl = get_template('session_feedback.html')
		f = open("%s/%s.html" % (self.confname, self.row[1].replace('/','-')), "w")
		f.write(tmpl.render(Context({
			'ratings': self.ratings,
			'comments': comments,
			'count': count,
			'session': {
				'name': self.row[1],
				'speaker': self.row[2],
			},
		})).encode('utf-8'))
		f.close()

	def fetch_graphs(self):
		return self.ratings

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
	psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
	db = psycopg2.connect(connstr)
	curs = db.cursor()
	curs.execute("SELECT id FROM confreg_conference WHERE urlname=%(url)s", {'url': confname})
	try:
		confid = curs.fetchall()[0][0]
	except:
		print "Could not find conference in database!"
		sys.exit(1)

# Generate global feedback
	# Global ratings
	ss = SessionStats(db, confid, confname, None)
	ss.calculate()
	graphs = ss.fetch_graphs()

	# Global comments
	curs.execute("""SELECT s.title, f.conference_feedback, spk.fullname
FROM confreg_conferencesessionfeedback f
INNER JOIN confreg_conferencesession s ON f.session_id=s.id
INNER JOIN confreg_conferencesession_speaker cs ON s.id=cs.conferencesession_id
INNER JOIN confreg_speaker spk ON spk.id=cs.speaker_id
WHERE s.conference_id=%(confid)s AND NOT f.conference_feedback=''
ORDER BY s.title, f.conference_feedback""",
		{'confid': confid})
	session_comments = [{'session': s, 'comment': c, 'speaker': sp} for s,c,sp in curs.fetchall()]

	# Speaker ratings
	speaker_rating = []
	for rating, ratingname in (('speaker_quality','Speaker Quality'),('speaker_knowledge','Speaker Knowledge'),):
		curs.execute("SELECT spk.fullname, avg("+rating+"), count(*), stddev("+rating+""")
FROM confreg_conferencesessionfeedback f
INNER JOIN confreg_conferencesession s ON f.session_id=s.id
INNER JOIN confreg_conferencesession_speaker cs ON s.id=cs.conferencesession_id
INNER JOIN confreg_speaker spk ON spk.id=cs.speaker_id
WHERE s.conference_id=%(confid)s AND """+rating+" >= 1 AND "+rating+""" <= 5
GROUP BY spk.fullname
ORDER BY 2 DESC
""", {'confid': confid})
		speaker_rating.append({'what': ratingname, 'rating': [{'speaker': s, 'quality': q, 'num': n, 'stddev': d} for s,q,n,d in curs.fetchall()]})


	# Now generate the file
	tmpl = get_template('conference_feedback.html')
	f = open("%s_conference.html" % confname, "w")
	f.write(tmpl.render(Context({
		'global_ratings': graphs,
		'session_comments': session_comments,
		'speaker_rating': speaker_rating,
	})).encode('utf-8'))
	f.close()

# Generate per-session feedback
	curs.execute("""SELECT s.id, title, fullname FROM confreg_conferencesession s
INNER JOIN confreg_conferencesession_speaker cs ON s.id=cs.conferencesession_id
INNER JOIN confreg_speaker spk ON spk.id=cs.speaker_id
WHERE conference_id=%(conf)s ORDER BY id
""", {'conf': confid})
	while True:
		row = curs.fetchone()
		if not row: break
		ss = SessionStats(db, confid, confname, row)
		ss.generate()

