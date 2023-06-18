# Verify balance on plaid accounts
#
# Copyright (C) 2023, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from django.conf import settings

from postgresqleu.invoices.models import InvoicePaymentMethod, PendingBankTransaction
from postgresqleu.accounting.util import get_latest_account_balance
from postgresqleu.mailqueue.util import send_simple_mail

import datetime
from decimal import Decimal


class Command(BaseCommand):
    help = 'Verify Plaid balancse'

    class ScheduledJob:
        scheduled_times = [datetime.time(3, 25), ]

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.plaid.Plaid', config__verify_balances=True).exists()

    @transaction.atomic
    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.plaid.Plaid', config__verify_balances=True):
            self.handle_method(method)

    def handle_method(self, method):
        impl = method.get_implementation()

        balances = impl.get_account_balances()
        if len(balances) != 1:
            raise Exception("Expected one account, got {}".format(len(balances)))
        plaid_balance = balances[0]['balance']

        accounting_balance = get_latest_account_balance(impl.config('bankaccount'))

        pending = PendingBankTransaction.objects.filter(method=method).aggregate(sum=Sum('amount'))['sum'] or Decimal(0)
        if accounting_balance + pending != plaid_balance:
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             impl.config('notification_receiver'),
                             'Plaid balance mismatch!',
                             """Plaid balance ({0}) for {1} does not match the accounting system ({2})!

This could be because some entry has been missed in the accounting
(automatic or manual), or because of an ongoing booking of something
that the system doesn't know about.

Better go check manually!
""".format(plaid_balance, method.internaldescription, accounting_balance + pending))
