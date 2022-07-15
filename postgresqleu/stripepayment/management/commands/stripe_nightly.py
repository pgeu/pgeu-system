#
# This script handles general nightly jobs for the Stripe integration:
#
#  * Expire old checkout sessions
#  * Compare balance to accounting
#  * Check for stalled refunds
#  * Send logs
#
# Copyright (C) 2019, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings
from django.utils import timezone

from datetime import time, timedelta
from io import StringIO

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.stripepayment.models import StripeCheckout, StripeRefund, StripeLog
from postgresqleu.stripepayment.api import StripeApi
from postgresqleu.accounting.util import get_latest_account_balance
from postgresqleu.mailqueue.util import send_simple_mail


class Command(BaseCommand):
    help = 'Stripe payment nightly job'

    class ScheduledJob:
        scheduled_times = [time(3, 00), ]

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.stripe.Stripe').exists()

    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.stripe.Stripe'):
            self.handle_one_account(method)

    @transaction.atomic
    def handle_one_account(self, method):
        pm = method.get_implementation()

        self.expire_sessions(method, pm)
        self.verify_balance(method, pm)
        self.check_refunds(method, pm)
        self.send_logs(method, pm)

    def expire_sessions(self, method, pm):
        # If there are any sessions that have not been touched for 48+ hours, then clearly something
        # went wrong, so just get rid of them.
        for co in StripeCheckout.objects.filter(paymentmethod=method, completedat__isnull=True, createdat__lt=timezone.now() - timedelta(hours=48)):
            StripeLog(message="Expired checkout session {0} (id {1}), not completed for 48 hours.".format(co.id, co.sessionid),
                      paymentmethod=method).save()
            co.delete()

    def verify_balance(self, method, pm):
        # Verify the balance against Stripe
        api = StripeApi(pm)
        stripe_balance = api.get_balance()
        accounting_balance = get_latest_account_balance(pm.config('accounting_income'))

        if accounting_balance != stripe_balance:
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Stripe balance mismatch!',
                             """Stripe balance ({0}) for {1} does not match the accounting system ({2})!

This could be because some entry has been missed in the accounting
(automatic or manual), or because of an ongoing booking of something
that the system doesn't know about.

Better go check manually!
""".format(stripe_balance, method.internaldescription, accounting_balance))

    def check_refunds(self, method, pm):
        for r in StripeRefund.objects.filter(paymentmethod=method,
                                             completedat__isnull=True,
                                             invoicerefundid__issued__lt=timezone.now() - timedelta(hours=6)):

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Stripe stalled refund!',
                             """Stripe refund {0} for {1} has been stalled for more than 6 hours!

This is probably not normal and should be checked!
""".format(r.id, method.internaldescription))

    def send_logs(self, method, pm):
        # Send logs for this account
        lines = list(StripeLog.objects.filter(error=True, sent=False, paymentmethod=method).order_by('timestamp'))
        if len(lines):
            sio = StringIO()
            sio.write("The following error events have been logged by the Stripe integration for {0}:\n\n".format(method.internaldescription))
            for line in lines:
                sio.write("%s: %s\n" % (line.timestamp, line.message))
                line.sent = True
                line.save()
            sio.write("\n\n\nAll these events have now been tagged as sent, and will no longer be\nprocessed by the system in any way.\n")

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Stripe integration error report',
                             sio.getvalue())
