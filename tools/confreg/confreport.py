#!/usr/bin/env python
#
# Tool to generate a report of conference registrations and
# additional options.
#
import sys
import os
import psycopg2
import psycopg2.extensions
import datetime
from StringIO import StringIO
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def Usage():
	print "Usage: confreport.py <connectionstring> <conferenceshortname> [mailaddr]"
	sys.exit(1)

if __name__ == "__main__":
	if len(sys.argv) != 3 and len(sys.argv) != 4:
		Usage()
	connstr = sys.argv[1]
	confname = sys.argv[2]

	psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
	db = psycopg2.connect(connstr)
	curs = db.cursor()
	curs.execute("SELECT id,conferencename FROM confreg_conference WHERE urlname=%(url)s", {'url': confname})
	try:
		r = curs.fetchall()[0]
		confid = r[0]
		confname = r[1]
	except:
		print "Could not find conference in database!"
		sys.exit(1)

	s = StringIO()
	s.writelines("Status for %s per %s\n\n\n" % (confname, datetime.datetime.now()))
	
	curs.execute("""
SELECT regtype,
       SUM(CASE WHEN payconfirmedat IS NOT NULL THEN 1 ELSE 0 END) AS paid,
       SUM(CASE WHEN payconfirmedat IS NULL THEN 1 ELSE 0 END) AS nonpaid
FROM confreg_conferenceregistration cr
INNER JOIN confreg_registrationtype rt ON cr.regtype_id=rt.id
WHERE cr.conference_id=%(id)s
GROUP BY regtype
ORDER BY 1,2
""", { 'id': confid })
	s.writelines("Registrations per type\n")
	s.writelines("----------------------\n")
	s.writelines("%-50s %13s %13s\n" % ('Type', 'Confirmed', 'Unconfirmed'))
	rows = curs.fetchall()
	s.writelines(["%-50s %13s %13s\n" % r for r in rows])
	s.writelines("%-50s %13s %13s\n" % ("", "------", "------"))
	s.writelines("%-50s %13s %13s\n" % ("Total",
										sum([r[1] for r in rows]),
										sum([r[2] for r in rows])))

	curs.execute("""
SELECT name,
       SUM(CASE WHEN payconfirmedat IS NOT NULL THEN 1 ELSE 0 END) AS paid,
       SUM(CASE WHEN payconfirmedat IS NULL THEN 1 ELSE 0 END) AS nonpaid
FROM confreg_conferenceadditionaloption cao
INNER JOIN confreg_conferenceregistration_additionaloptions cr_ao ON cao.id=cr_ao.conferenceadditionaloption_id
INNER JOIN confreg_conferenceregistration cr ON cr.id=cr_ao.conferenceregistration_id
WHERE cao.conference_id=%(id)s
GROUP BY name
ORDER BY 1
""", { 'id': confid })
	s.writelines("\n")
	s.writelines("Additional options\n")
	s.writelines("------------------\n")
	s.writelines("%-50s %13s %13s\n" % ('Type', 'Confirmed', 'Unconfirmed'))
	rows = curs.fetchall()
	s.writelines(["%-50s %13s %13s\n" % (r[0][:50],r[1],r[2]) for r in rows])
	s.writelines("%-50s %13s %13s\n" % ("", "------", "------"))
	s.writelines("%-50s %13s %13s\n" % (" Total",
										sum([r[1] for r in rows]),
										sum([r[2] for r in rows])))

	if len(sys.argv) == 4:
		# send email
		msg = MIMEMultipart()
		msg['Subject'] = "%s registration report" % confname
		msg['From'] = 'webmaster@postgresql.eu'
		msg['To'] = sys.argv[3]
		msg.attach(MIMEText(s.getvalue().encode('utf-8'), 'plain', 'UTF-8'))

		s = smtplib.SMTP()
		s.connect()
		s.sendmail("webmaster@postgresql.eu", [sys.argv[3]], msg.as_string())
		s.quit()
	else:
		# Don't send email, so just print it
		print s.getvalue()
