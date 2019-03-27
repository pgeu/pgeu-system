#
# This script compares the balance of a TransferWise account with the
# one in the accounting system, raising an alert if they are different
# (which indicates that something has been incorrectly processed).
#
# Copyright (C) 2019, PostgreSQL Europe
#


from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from datetime import time

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.accounting.util import get_latest_account_balance
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.transferwise.api import TransferwiseApi


class Command(BaseCommand):
    help = 'Compare TransferWise balance to the accounting system'

    class ScheduledJob:
        scheduled_times = [time(3, 15), ]

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.transferwise.Transferwise').exists()

    @transaction.atomic
    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.transferwise.Transferwise'):
            self.verify_one_account(method)

    def verify_one_account(self, method):
        method = method
        pm = method.get_implementation()

        api = TransferwiseApi(pm)

        tw_balance = api.get_balance()

        accounting_balance = get_latest_account_balance(pm.config('bankaccount'))

        if accounting_balance != tw_balance:
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             settings.TREASURER_EMAIL,
                             'TransferWise balance mismatch!',
                             """TransferWise balance ({0}) for {1} does not match the accounting system ({2})!

This could be because some entry has been missed in the accounting
(automatic or manual), or because of an ongoing booking of something
that the system doesn't know about.

Better go check manually!
""".format(tw_balance, method.internaldescription, accounting_balance))
