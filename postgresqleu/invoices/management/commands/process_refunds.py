# Process queued up refunds
#
# Automated refunds are always processed out of line to make sure
# we don't timeout in API calls or similar, and return speedy to
# the browser. Cronjob is expected to run at regular intervals of
# a few hours.
#
# Copyright (C) 2016, PostgreSQL Europe
#

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

from postgresqleu.invoices.models import InvoiceRefund
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.mailqueue.util import send_simple_mail

from datetime import datetime, timedelta


class Command(BaseCommand):
    help = 'Send off API-based refunds'

    def handle(self, *args, **options):
        refunds = InvoiceRefund.objects.filter(issued__isnull=True)
        for r in refunds:
            manager = InvoiceManager()

            # One transaction for each object, and make sure it's properly
            # locked by using select for update, in case we get a notification
            # delivered while we are still processing.
            with transaction.atomic():
                rr = InvoiceRefund.objects.select_for_update().filter(pk=r.pk)[0]
                if not rr.invoice.can_autorefund:
                    # How did we end up in the queue?!
                    raise CommandError("Invoice {0} listed for refund, but provider is not capable of refunds!".format(r.invoice.id))

                # Calling autorefund will update the InvoiceRefund object
                # after calling the APIs, so nothing more to do here.

                manager.autorefund_invoice(rr)

                self.stdout.write("Issued API refund of invoice {0}.".format(rr.invoice.pk))

        # Send alerts for any refunds that have been issued but that have not completed within
        # 3 days (completely arbitrary, but normally it happens within seconds/minutes/hours).
        stalledrefunds = InvoiceRefund.objects.filter(issued__isnull=False, completed__isnull=True,
                                                      issued__lt=datetime.now() - timedelta(days=3))
        if stalledrefunds:
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             settings.INVOICE_SENDER_EMAIL,
                             "Stalled invoice refunds",
                             """One or more invoice refunds appear to be stalled.
These refunds have been issued to the provider, but no confirmation has
shown up. This requires manual investigation.

The following invoices have stalled refunds:

{0}

Better go check!
""".format("\n".join([r.invoice.invoicestr for r in stalledrefunds])))
