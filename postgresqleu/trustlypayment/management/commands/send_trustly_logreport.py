# This script sends out reports of errors in the Trustly integration as
# a summary email.
#
# Copyright (C) 2016, PostgreSQL Europe
#
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.core import urlresolvers
from django.conf import settings

from datetime import datetime, timedelta
from StringIO import StringIO

from postgresqleu.trustlypayment.models import TrustlyLog, TrustlyNotification, TrustlyTransaction
from postgresqleu.mailqueue.util import send_simple_mail

class Command(BaseCommand):
	help = 'Send log information about Trustly events'

	def handle(self, *args, **options):
		self.report_loglines()
		self.report_unconfirmed_notifications()
		self.report_unfinished_transactions()

	@transaction.atomic
	def report_loglines(self):
		lines = list(TrustlyLog.objects.filter(error=True,sent=False).order_by('timestamp'))
		if len(lines):
			sio = StringIO()
			sio.write("The following error events have been logged by the Trustly integration:\n\n")
			for l in lines:
				sio.write("%s: %s\n" % (l.timestamp, l.message))
				l.sent = True
				l.save()
			sio.write("\n\n\nAll these events have now been tagged as sent, and will no longer be\nprocessed by the system in any way.\n")

			send_simple_mail(settings.INVOICE_SENDER_EMAIL,
							 settings.TRUSTLY_NOTIFICATION_RECEIVER,
							 'Trustly integration error report',
							 sio.getvalue())

	def report_unconfirmed_notifications(self):
		lines = list(TrustlyNotification.objects.filter(confirmed=False, receivedat__lt=datetime.now()-timedelta(days=1)).order_by('receivedat'))
		if len(lines):
			sio = StringIO()
			sio.write("The following notifications have not been confirmed in the Trustly integration.\nThese need to be manually processed and then flagged as confirmed!\n\nThis list only contains unconfirmed events older than 24 hours.\n\n\n")
			for l in lines:
				sio.write("%s: %s (%s%s)\n" % (l.receivedat, l.method, settings.SITEBASE, urlresolvers.reverse('admin:trustlypayment_trustlynotification_change', args=(l.id,))))

			send_simple_mail(settings.INVOICE_SENDER_EMAIL,
							 settings.TRUSTLY_NOTIFICATION_RECEIVER,
							 'Trustly integration unconfirmed notifications',
							 sio.getvalue())

	def report_unfinished_transactions(self):
		# Number of days until we start reporting unfinished transactions
		# Note: we only care about transactions that have actually started, where the user
		# got the first step of confirmation. The ones that were never started are uninteresting.
		UNFINISHED_THRESHOLD=3

		lines = list(TrustlyTransaction.objects.filter(completedat__isnull=True, pendingat__isnull=False, pendingat__lt=datetime.now()-timedelta(days=UNFINISHED_THRESHOLD)).order_by('pendingat')
		if len(lines):
			sio = StringIO()
			sio.write("The following payments have been authorized, but not finished for more than %s days.\nThese probably need to be verified manually.\n\n\n" % UNFINISHED_THRESHOLD)

			for l in lines:
				sio.write("%s at %s: %s (%s%s)\n" % (orderid, l.pendingat, l.amount, settings.SITEBASE, urlresolvers.reverse('admin:trustlypayment_trustlytransactionstatus_change', args=(l.id,))))

			send_simple_mail(settings.INVOICE_SENDER_EMAIL,
							 settings.TRUSTLY_NOTIFICATION_RECEIVER,
							 'Trustly integration unconfirmed notifications',
							 sio.getvalue())

