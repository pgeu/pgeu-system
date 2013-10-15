#!/usr/bin/env python
#
# Script to send off all queued email.
#
# This script is intended to be run frequently from cron. We queue things
# up in the db so that they get automatically rolled back as necessary,
# but once we reach this point we're just going to send all of them one
# by one.
#

import sys
import os
import smtplib

# Set up to run in django environment
from django.core.management import setup_environ
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../postgresqleu'))
import settings
setup_environ(settings)

from django.db import connection, transaction

from postgresqleu.mailqueue.models import QueuedMail

def _sendmail(msg):
	smtp = smtplib.SMTP("localhost")
	smtp.sendmail(msg['From'], msg['To'], msg.as_string())
	smtp.close()


if __name__ == "__main__":
	# Grab advisory lock, if available. Lock id is just a random number
	# since we only need to interlock against ourselves. The lock is
	# automatically released when we're done.
	curs = connection.cursor()
	curs.execute("SELECT pg_try_advisory_lock(72181378)")
	if not curs.fetchall()[0][0]:
		print "Failed to get advisory lock, existing send_queued_mail process stuck?"
		sys.exit(1)

	for m in QueuedMail.objects.all():
		# Yes, we do a new connection for each run. Just because we can.
		# If it fails we'll throw an exception and just come back on the
		# next cron job. And local delivery should never fail...
		smtp = smtplib.SMTP("localhost")
		smtp.sendmail(m.sender, m.receiver, m.fullmsg.encode('utf-8'))
		smtp.close()
		m.delete()
		transaction.commit()
	connection.close()
