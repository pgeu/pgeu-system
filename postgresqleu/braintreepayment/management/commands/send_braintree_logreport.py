# This script sends out reports fo errors in the Braintree integration
# as a summary email.
#
# Copyright (C) 2015, PostgreSQL Europe
#
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from StringIO import StringIO

from postgresqleu.braintreepayment.models import BraintreeLog
from postgresqleu.mailqueue.util import send_simple_mail

class Command(BaseCommand):
	help = 'Send log information about Braintree events'

	def handle(self, *args, **options):
		with transaction.atomic():
			lines = list(BraintreeLog.objects.filter(error=True,sent=False).order_by('timestamp'))

		if len(lines):
			sio = StringIO()
			sio.write("The following error events have been logged by the Braintree integration:\n\n")
			for l in lines:
				sio.write("%s: %20s: %s\n" % (l.timestamp, l.transid, l.message))
				l.sent = True
				l.save()
			sio.write("\n\n\nAll these events have now been tagged as sent, and will no longer be\nprocessed by the system in any way.\n")

			send_simple_mail(settings.INVOICE_SENDER_EMAIL,
							 settings.BRAINTREE_NOTIFICATION_RECEIVER,
							 'Braintree integration error report',
							 sio.getvalue())
