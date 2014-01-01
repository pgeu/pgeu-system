#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This script sends out reports of activity and errors in the paypal integration,
# as well as a list of any unmatched payments still in the system.

# Copyright (C) 2010, PostgreSQL Europe

import psycopg2
import psycopg2.extras
import sys
import ConfigParser

from subprocess import Popen, PIPE
from email.mime.text import MIMEText

def sendmail(msg):
	pipe = Popen("/usr/sbin/sendmail -t", shell=True, stdin=PIPE).stdin
	pipe.write(msg.as_string())
	pipe.close()


if __name__ == "__main__":
	if len(sys.argv) != 2:
		print "Usage: report.py <dsn>"
		sys.exit(1)

	cfg = ConfigParser.ConfigParser()
	cfg.read('paypal.ini')

	db = psycopg2.connect(sys.argv[1])
	cursor = db.cursor(cursor_factory=psycopg2.extras.DictCursor)

	# Generate report emails with events, if there are any
	cursor.execute('SELECT id, "timestamp", message FROM paypal_errorlog WHERE NOT sent ORDER BY id')
	res = cursor.fetchall()
	if res:
		msg = MIMEText("""
Events reported by the paypal integration:

%s
""" % "\n".join(["%s: %s" % (r['timestamp'], r['message']) for r in res]), _charset = 'utf-8')
		msg['subject'] = 'PostgreSQL Europe Paypal Integration Report'
		msg['from'] = cfg.get('_mail', 'sender')
		msg['to'] = cfg.get('_mail', 'reports')
		sendmail(msg)
		cursor.execute("UPDATE paypal_errorlog SET sent='t' WHERE NOT sent")
		db.commit()

	# Generate report of unmatched payments, if there are any.
	cursor.execute('SELECT "timestamp", sender, sendername, amount, transtext FROM paypal_transactioninfo WHERE NOT matched ORDER BY "timestamp"')
	res = cursor.fetchall()
	if res:
		msg = MIMEText("""
The following payments have been received but not matched to anything in
the system:

%s

These will keep being reported until there is a match found or they are
manually dealt with in the admin interface!
""" % "\n".join(["%s: %s (%s) sent %s with text '%s'" % (r['timestamp'], r['sender'], r['sendername'], r['amount'], r['transtext']) for r in res]), _charset='utf-8')
		msg['subject'] = 'PostgreSQL Europe Paypal Unmatched Transactions'
		msg['from'] = cfg.get('_mail', 'sender')
		msg['to'] = cfg.get('_mail', 'reports')
		sendmail(msg)
