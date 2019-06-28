#
# This script compares the balance of a TransferWise account with the
# one in the accounting system, raising an alert if they are different
# (which indicates that something has been incorrectly processed).
#
# If auto payout is enabled, will also schedule an automatic payout to
# bank account if thresholds are exceeded.
#
# Copyright (C) 2019, PostgreSQL Europe
#


from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from django.conf import settings

import datetime
import time
from decimal import Decimal
import uuid

from postgresqleu.invoices.models import InvoicePaymentMethod, PendingBankTransaction
from postgresqleu.accounting.util import get_latest_account_balance
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.transferwise.api import TransferwiseApi
from postgresqleu.transferwise.models import TransferwisePayout
from postgresqleu.util.checksum import luhn


class Command(BaseCommand):
    help = 'Compare TransferWise balance to the accounting system and make optional payouts'

    class ScheduledJob:
        scheduled_times = [datetime.time(3, 15), ]

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

        # Pending bank transactions are included in the tw_balance, but they are *not* yet
        # in the accounting system (that's the definition of being pending..)
        pending = PendingBankTransaction.objects.filter(method=method).aggregate(sum=Sum('amount'))['sum'] or Decimal(0)

        if accounting_balance + pending != tw_balance:
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             settings.TREASURER_EMAIL,
                             'TransferWise balance mismatch!',
                             """TransferWise balance ({0}) for {1} does not match the accounting system ({2})!

This could be because some entry has been missed in the accounting
(automatic or manual), or because of an ongoing booking of something
that the system doesn't know about.

Better go check manually!
""".format(tw_balance, method.internaldescription, accounting_balance + pending))

        # If balance matches, possibly check if we should trigger an automatic payout
        if pm.config('autopayout'):
            if tw_balance > pm.config('autopayouttrigger'):
                # There is more money in the account than we need!
                # If there is an existing Payout that has not yet been sent,
                # we don't risk sending one more, we wait until that one is
                # completed.
                if TransferwisePayout.objects.filter(paymentmethod=method, completedat__isnull=True):
                    self.stdout.write("Not sending payout for {0}, there is already a pending payout.".format(method.internaldescription))
                    return

                # Creat a payout down to the limited amount
                amount = tw_balance - pm.config('autopayoutlimit')

                # Generate a unique reference (unique enough)
                refno = "{}{}".format(int(time.time() % 100000), method.id)
                refno = refno + str(luhn(refno))

                payout = TransferwisePayout(
                    paymentmethod=method,
                    amount=amount,
                    reference='TW payout {0}'.format(refno),
                    counterpart_name=pm.config('autopayoutname'),
                    counterpart_account=pm.config('autopayoutiban'),
                    uuid=uuid.uuid4())
                payout.save()

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             settings.TREASURER_EMAIL,
                             'TransferWise payout triggered',
                             """TransferWise balance ({0}) for {1} exceeded {2}.
An automatic payout of {3} has been initiated, bringing the
balance down to {4}.
""".format(tw_balance, method.internaldescription, pm.config('autopayouttrigger'), amount, pm.config('autopayoutlimit')))
