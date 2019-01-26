from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.invoices.models import Invoice
from postgresqleu.trustlypayment.models import TrustlyTransaction, TrustlyLog

from datetime import timedelta


class Command(BaseCommand):
    help = 'Extend trustly invoices if they are in pending state'

    class ScheduledJob:
        scheduled_interval = timedelta(hours=1)
        internal = True

        @classmethod
        def should_run(self):
            return TrustlyTransaction.objects.filter(pendingat__isnull=False, completedat__isnull=True).exists()

    def handle(self, *args, **options):
        manager = InvoiceManager()
        with transaction.atomic():
            for trans in TrustlyTransaction.objects.filter(pendingat__isnull=False, completedat__isnull=True):
                # Pending is set, completed is not set, means we are waiting for a slow transaction.
                try:
                    invoice = Invoice.objects.get(pk=trans.invoiceid)
                except Invoice.DoesNotExist:
                    raise CommandError("Invoice {0} for order {1} not found!".format(trans.invoiceid, trans.orderid))

                # Make sure the invoice is valid for at least another 24 hours (yay banks that only
                # sync their data once a day)
                # If the invoice is extended, email is sent to invoice admins, but not end users.
                r = manager.postpone_invoice_autocancel(invoice,
                                                        timedelta(hours=24),
                                                        "Trustly payment still in pending, awaiting credit",
                                                        silent=False)
                if r:
                    TrustlyLog(message="Extended autocancel time for invoice {0} to ensure time for credit notification".format(invoice.id),
                               paymentmethod=trans.paymentmethod).save()
