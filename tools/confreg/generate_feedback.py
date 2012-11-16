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
	chart.set_title(measurement.encode('utf-8'))
	chart.add_data(n)
	if not labels:
		# 1,2,3,4,5 and with the percentage
		labels = ["%s (%s%%)" % (v, round(n[v-1]*100/s,1)) for v in range (1,6)]
	else:
		# We have text labels, assume same order as values
		labels = ["%s (%s%%)" % (labels[v-1].encode('utf-8'), round(n[v-1]*100/s)) for v in range(1,len(labels)+1)]

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
		f = open("%s/%s.html" % (self.confname, self.row[1].replace('/','-').encode('ascii', 'replace').replace('?','')), "w")
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
AND s.status=1 AND can_feedback
GROUP BY spk.fullname
ORDER BY 2 DESC
""", {'confid': confid})
		speaker_rating.append({'what': ratingname, 'rating': [{'speaker': s, 'quality': q, 'num': n, 'stddev': d} for s,q,n,d in curs.fetchall()]})


# Generate per-session feedback
# sync with send_feedback.py
	curs.execute("""SELECT s.id, title, fullname FROM confreg_conferencesession s
INNER JOIN confreg_conferencesession_speaker cs ON s.id=cs.conferencesession_id
INNER JOIN confreg_speaker spk ON spk.id=cs.speaker_id
WHERE conference_id=%(conf)s AND s.can_feedback AND s.status=1
ORDER BY id
""", {'conf': confid})
	while True:
		row = curs.fetchone()
		if not row: break
		ss = SessionStats(db, confid, confname, row)
		ss.generate()

# Generate full-conference feedback, if there is any
	curs.execute("""SELECT id, question, isfreetext, newfieldset, textchoices FROM confreg_conferencefeedbackquestion WHERE conference_id=%(conf)s ORDER BY sortkey""", {'conf': confid})
	questions = curs.fetchall()

	if len(questions):
		# This is basically an EAV schema, so do it the hard way,
		# with one query for each question.
		responses = {}
		currentfieldset = ''
		for id, question, isfreetext, newfieldset, textchoices in questions:
			if newfieldset:
				# This is only set for the first row in each group, so it's
				# always correct.
				currentfieldset = newfieldset
				responses[currentfieldset] = []
			if isfreetext and not textchoices:
				curs.execute("""SELECT textanswer FROM confreg_conferencefeedbackanswer WHERE question_id=%(qid)s AND textanswer IS NOT NULL AND NOT trim(textanswer)=''""", {'qid': id})
				responses[currentfieldset].append({
						'question': question,
						'textanswers': [x[0] for x in curs.fetchall()],
					})
			elif isfreetext:
				# Freetext but with fixed choices, generate graph
				curs.execute("""SELECT textanswer,count(*) FROM confreg_conferencefeedbackanswer WHERE question_id=%(qid)s AND textanswer IS NOT NULL GROUP BY textanswer ORDER BY textanswer""", {'qid': id})
				rows = curs.fetchall()
				responses[currentfieldset].append({
						'question': question,
						'graph': generate_pie_graph(question,
													[float(x[1]) for x in rows],
													[x[0] for x in rows]),
				})
			else:
				# Rateanswer
				curs.execute("""SELECT rateanswer,sum(count) FROM (SELECT rateanswer,count(*) FROM confreg_conferencefeedbackanswer WHERE question_id=%(qid)s GROUP BY rateanswer UNION ALL SELECT g,0 FROM generate_series(0,5) g) foo GROUP BY rateanswer ORDER BY rateanswer""", {'qid': id})
				responses[currentfieldset].append({
						'question': question,
						'graph': generate_pie_graph(question,
													[float(x[1]) for x in curs.fetchall()],
													[str(x) for x in range(0,6)])
				})

	else:
		responses = None


	# Now generate the global conference feedback file
	tmpl = get_template('conference_feedback.html')
	f = open("%s_conference.html" % confname, "w")
	f.write(tmpl.render(Context({
		'global_ratings': graphs,
		'session_comments': session_comments,
		'speaker_rating': speaker_rating,
		'conference_responses': responses,
	})).encode('utf-8'))
	f.close()
