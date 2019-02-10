#
# This script tracks withdrawals from Trustly into main bank account.
#
# Copyright (C) 2019 PostgreSQL Europe
#


from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from datetime import time, datetime, timedelta

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.trustlypayment.util import Trustly
from postgresqleu.trustlypayment.models import TrustlyWithdrawal, TrustlyLog


class Command(BaseCommand):
    help = 'Fetch Trustly withdrawals'

    class ScheduledJob:
        scheduled_times = [time(22, 00), ]

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.trustly.TrustlyPayment').exists()

    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.trustly.TrustlyPayment'):
            self.fetch_one_account(method)

    @transaction.atomic
    def fetch_one_account(self, method):
        pm = method.get_implementation()

        trustly = Trustly(pm)

        transactions = trustly.getledgerforrange(datetime.today() - timedelta(days=7), datetime.today())

        for t in transactions:
            if t['accountname'] == 'BANK_WITHDRAWAL_QUEUED' and not t['orderid']:
                # If it has an orderid, it's a refund, but if not, then it's a transfer out (probably)
                w, created = TrustlyWithdrawal.objects.get_or_create(paymentmethod=method,
                                                                     gluepayid=t['gluepayid'],
                                                                     defaults={
                                                                         amount: -Decimal(t['amount']),
                                                                         message: t['messageid'],
                                                                     },
                )
                w.save()

                if created:
                    TrustlyLog(message='New bank withdrawal of {0} found'.format(-Decimal(t['amount'])),
                               paymentmethod=method).save()

                    accstr = 'Transfer from Trustly to bank'
                    accrows = [
                        (pm.config('accounting_income'), accstr, w.amount, None),
                        (pm.config('accounting_transfer'), accstr, -w.amount, None),
                    ]
                    entry = create_accounting_entry(t['timestamp'].date(),
                                                    accrows,
                                                    dateutil.parser.parse(w['datestamp']),
                                                    [],
                    )
                    if is_managed_bank_account(pm.config('accounting_transfer')):
                        register_pending_bank_matcher(pm.config('accounting_transfer'),
                                                      '.*TRUSTLY.*{0}.*'.format(w.gluepayid),
                                                      -w.amount,
                                                      entry)
