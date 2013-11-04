#!/usr/bin/env python
#
# This script sends out reports of errors in the Adyen integration as
# a summary email.
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

from datetime import datetime, timedelta
from StringIO import StringIO

from django.db import transaction, connection
from django.core import urlresolvers

from postgresqleu.adyen.models import AdyenLog, Notification
from postgresqleu.mailqueue.util import send_simple_mail


@transaction.commit_on_success
def report_loglines():
	lines = list(AdyenLog.objects.filter(error=True,sent=False).order_by('timestamp'))
	if len(lines):
		sio = StringIO()
		sio.write("The following error events have been logged by the Adyen integration:\n\n")
		for l in lines:
			sio.write("%s: %20s: %s\n" % (l.timestamp, l.pspReference, l.message))
			l.sent = True
			l.save()
		sio.write("\n\n\nAll these events have now been tagged as sent, and will no longer be\nprocessed by the system in any way.\n")

		send_simple_mail(settings.INVOICE_SENDER_EMAIL,
						 settings.ADYEN_NOTIFICATION_RECEIVER,
						 'Adyen integration error report',
						 sio.getvalue())

def report_unconfirmed_notifications():
	lines = list(Notification.objects.filter(confirmed=False, receivedat__lt=datetime.now()-timedelta(days=1)).order_by('eventDate'))
	if len(lines):
		sio = StringIO()
		sio.write("The following notifications have not been confirmed in the Adyen integration.\nThese need to be manually processed and then flagged as confirmed!\n\nThis list only contains unconfirmed events older than 24 hours.\n\n\n")
		for l in lines:
			sio.write("%s: %s (%s%s)" % (l.eventDate, l.eventCode, settings.SITEBASE_SSL, urlresolvers.reverse('admin:adyen_notification_change', args=(l.id,))))

		send_simple_mail(settings.INVOICE_SENDER_EMAIL,
						 settings.ADYEN_NOTIFICATION_RECEIVER,
						 'Adyen integration unconfirmed notifications',
						 sio.getvalue())

if __name__=="__main__":
	report_loglines()
	report_unconfirmed_notifications()
	connection.close()
