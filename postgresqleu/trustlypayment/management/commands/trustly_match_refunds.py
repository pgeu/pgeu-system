#
# Trustly does not send notifications on refunds completed (they just
# give success as response to API call). For this reason, we have this
# script that polls to check if a refund has completed successfully.
#
# Copyright (C) 2010-2018, PostgreSQL Europe
#


from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

from postgresqleu.trustlypayment.util import Trustly
from postgresqleu.trustlypayment.models import TrustlyTransaction, TrustlyLog
from postgresqleu.invoices.models import InvoiceRefund, InvoicePaymentMethod
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.mailqueue.util import send_simple_mail

from decimal import Decimal

class Command(BaseCommand):
	help = 'Verify that a Trustly refund has completed, and flag it as such'

	@transaction.atomic
	def handle(self, *args, **options):
		trustly = Trustly()
		manager = InvoiceManager
		method = InvoicePaymentMethod.objects.get(classname='postgresqleu.util.payment.trustly.TrustlyPayment')

		refunds = InvoiceRefund.objects.filter(completed__isnull=True, invoice__paidusing=method)

		for r in refunds:
			# Find the matching Trustly transaction
			trustlytransactionlist = list(TrustlyTransaction.objects.filter(invoiceid=r.invoice.pk))
			if len(trustlytransactionlist) == 0:
				raise CommandError("Could not find trustly transaction for invoice {0}".format(r.invoice.pk))
			elif len(trustlytransactionlist) != 1:
				raise CommandError("Found {0} trustly transactions for invoice {1}!".format(len(trustlytransactionlist), r.invoice.pk))
			trustlytrans = trustlytransactionlist[0]
			w = trustly.getwithdrawal(trustlytrans.orderid)
			if not w:
				# No refund yet
				continue

			if w['transferstate'] != 'CONFIRMED':
				# Still pending
				continue

			if Decimal(w['amount']) != r.fullamount:
				raise CommandError("Mismatch in amount on Trustly refund for invoice {0}".format(r.invoice.pk))

			# Ok, things look good!
			TrustlyLog(message="Refund for order {0}, invoice {1}, completed".format(trustlytrans.orderid, r.invoice.pk), error=False).save()
			manager.complete_refund(
				r.id,
				Decimal(w['amount']),
				0,
				settings.ACCOUNTING_TRUSTLY_ACCOUNT,
				0, # We don't support fees on Trustly at this point
				[],
				method)
