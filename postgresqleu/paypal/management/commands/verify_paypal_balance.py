#
# This script compares the balance on the paypal account with the one
# in the accounting system, raising an alert if they are different
# (which indicates that something has been incorrectly processed).
#
# Copyright (C) 2010-2016, PostgreSQL Europe
#


from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from datetime import time

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.paypal.util import PaypalAPI
from postgresqleu.accounting.util import get_latest_account_balance
from postgresqleu.mailqueue.util import send_simple_mail


class Command(BaseCommand):
    help = 'Compare paypal balance to the accounting system'

    class ScheduledJob:
        scheduled_times = [time(3, 4), ]

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.paypal.Paypal').exists()

    @transaction.atomic
    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.paypal.Paypal'):
            pm = method.get_implementation()

            api = PaypalAPI(pm)

            # We only ever care about the primary currency
            paypal_balance = api.get_primary_balance()

            accounting_balance = get_latest_account_balance(pm.config('accounting_income'))

            if accounting_balance != paypal_balance:
                send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                                 pm.config('report_receiver'),
                                 'Paypal balance mismatch!',
                                 """Paypal balance ({0}) does not match the accounting system ({1}) for payment method {2}!

    This could be because some entry has been missed in the accouting
    (automatic or manual), or because of an ongoing booking of something
    that the system doesn't know about.

    Better go check manually!
    """.format(paypal_balance, accounting_balance, method.internaldescription))
