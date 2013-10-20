#!/usr/bin/env python
#
# Reprocess a *raw* notification, after the code for it has been modified,
# or for some other reason.
#
# Copyright (C) 2013, PostgreSQL Europe
#

import os
import sys

# Set up to run in django environment
from django.core.management import setup_environ
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../postgresqleu'))
import settings
setup_environ(settings)

from django.db import connection
from django.http import QueryDict
from postgresqleu.adyen.models import RawNotification, AdyenLog
from postgresqleu.adyen.util import process_raw_adyen_notification

def run():
	try:
		rawnotification = RawNotification.objects.get(pk=sys.argv[1])
	except RawNotification.DoesNotExist:
		print "Notification %s not found." % sys.argv[1]
		sys.exit(1)

	if rawnotification.confirmed:
		print "This raw notification is already processed!"
		sys.exit(1)

	# Rebuild a POST dictionary with the contents of this request
	POST = QueryDict(rawnotification.contents, "utf8")
	print POST

	AdyenLog(pspReference=rawnotification.id, message='Reprocessing RAW notification id %s' % rawnotification.id, error=False).save()

	process_raw_adyen_notification(rawnotification, POST)
	print "Completed reprocessing raw notification %s" % rawnotification.id

if __name__ == "__main__":
	if len(sys.argv) != 2:
		print "Usage: reprocess_raw_notification.py id"
		print " (note, uses the database internal id, check URL in admin interface)"
		sys.exit(1)

	run()
	connection.close()
