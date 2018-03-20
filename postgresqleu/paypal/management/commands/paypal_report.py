#
# This script sends out reports of activity and errors in the paypal
# integration, as well as a list of any unmatched payments still in
# the system.
#
# Copyright (C) 2010-2018, PostgreSQL Europe
#

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, connection
from django.conf import settings

from postgresqleu.paypal.models import ErrorLog, TransactionInfo
from postgresqleu.mailqueue.util import send_simple_mail

class Command(BaseCommand):
	help = 'Send paypal report emails'

	@transaction.atomic
	def handle(self, *args, **options):
		entries = ErrorLog.objects.filter(sent=False).order_by('id')
		if len(entries):
			msg = u"""
Events reported by the paypal integration:

{0}
""".format("\n".join([u"{0}: {1}".format(e.timestamp, e.message) for e in entries]))

			send_simple_mail(settings.INVOICE_SENDER_EMAIL,
							 settings.PAYPAL_REPORT_RECEIVER,
							 'Paypal Integration Report',
							 msg)
			entries.update(sent=True)

		entries = TransactionInfo.objects.filter(matched=False).order_by('timestamp')
		if len(entries):
			msg = u"""
The following payments have been received but not matched to anything in
the system:

{0}

These will keep being reported until there is a match found or they are
manually dealt with in the admin interface!
""".format("\n".join([u"{0}: {1} ({2}) sent {3} with text '{4}'".format(e.timestamp, e.sender, e.sendername, e.amount, e.transtext) for e in entries]))

			send_simple_mail(settings.INVOICE_SENDER_EMAIL,
							 settings.PAYPAL_REPORT_RECEIVER,
							 'Paypal Unmatched Transactions',
							 msg)
