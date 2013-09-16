#!/usr/bin/env python
#
# Reprocess a notification, after the code for it has been modified,
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

from django.db import transaction, connection
from postgresqleu.adyen.models import Notification, AdyenLog
from postgresqleu.adyen.util import process_one_notification

@transaction.commit_on_success
def run():
	try:
		notification = Notification.objects.get(pspReference=sys.argv[1])
	except Notification.DoesNotExist:
		print "Notification %s not found." % sys.argv[1]
		sys.exit(1)

	AdyenLog(pspReference=notification.pspReference, message='Reprocessing notification id %s' % notification.id, error=False).save()
	process_one_notification(notification)
	print "Completed reprocessing notification %s" % notification.pspReference

if __name__ == "__main__":
	if len(sys.argv) != 2:
		print "Usage: reprocess_notification.py <pspreference>"
		sys.exit(1)

	run()
	connection.close()
