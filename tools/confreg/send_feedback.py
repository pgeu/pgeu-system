#!/usr/bin/env python
#
# Tool to send feedback reports via email. Feedback reports should already
# be created using generate_feedback.py.
#
import sys
import os
import psycopg2
import psycopg2.extensions
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class Sender:
	def __init__(self, confdir, confname, sender, email, name):
		self.confdir = confdir
		self.confname = confname
		self.sender = sender
		self.email = email
		self.name = name
		self.sessions = []

	def append(self, session):
		session = session.replace('/','-').encode('ascii', 'replace').replace('?','')
		fn = "%s/%s.html" % (self.confdir, session)
		if not os.path.isfile(fn):
			raise "File %s not found" % fn
		self.sessions.append(session)

	def send(self):
		if not len(self.sessions):
			return

		msg = MIMEMultipart()
		msg['Subject'] = 'Conference feedback for %s' % self.confname
		msg['From'] = self.sender
		msg['To'] = self.email
		msg.attach(MIMEText("""
Attached you will find the feedback submitted for your session(s) at
%s.

If you have any questions, feel free to contact us!
""" % self.confname, _subtype='plain', _charset='utf-8'))

		for f in self.sessions:
			fp = open("%s/%s.html" % (self.confdir, f))
			att = MIMEText(fp.read(), _subtype='html', _charset='utf-8')
			fp.close()
			att.add_header('Content-Disposition', 'attachment', filename="%s.html" % f)
			msg.attach(att)

		print "Sending %i files to %s" % (len(self.sessions), self.email)
		s = smtplib.SMTP()
		s.connect()
		s.sendmail(self.sender, [self.email], msg.as_string())
		s.quit()

def Usage():
	print "Usage: send_feedbackup.py <connectionstring> <conferenceshortname> <fromemail> [only_send_to]"
	sys.exit(1)

if __name__ == "__main__":
	if len(sys.argv) != 4 and len(sys.argv) != 5:
		Usage()
	connstr = sys.argv[1]
	confdir = sys.argv[2]
	fromemail = sys.argv[3]
	if len(sys.argv) == 5:
		onlysendto = sys.argv[4]
	else:
		onlysendto = None

	psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
	db = psycopg2.connect(connstr)
	curs = db.cursor()
	curs.execute("SELECT id,conferencename FROM confreg_conference WHERE urlname=%(url)s", {'url': confdir})
	try:
		r = curs.fetchall()[0]
		confid = r[0]
		confname = r[1]
	except:
		print "Could not find conference in database!"
		sys.exit(1)

# Sync with generate_feedback.py!
	curs.execute("""SELECT title, fullname, email FROM confreg_conferencesession s
INNER JOIN confreg_conferencesession_speaker cs ON cs.conferencesession_id=s.id
INNER JOIN confreg_speaker spk ON spk.id=cs.speaker_id
INNER JOIN auth_user u ON u.id=spk.user_id
WHERE conference_id=%(conf)s AND can_feedback AND status=1
ORDER BY email
""", {'conf': confid})
	lastemail = ''
	sender = None
	while True:
		row = curs.fetchone()
		if not row: break
		title = row[0]
		name = row[1]
		email = row[2]

		if onlysendto:
			if not email == onlysendto:
				continue

		if email != lastemail:
			if sender: sender.send()
			sender = Sender(confdir, confname, fromemail, email, name)
			lastemail = email
		sender.append(title)
	if sender:
		sender.send()

