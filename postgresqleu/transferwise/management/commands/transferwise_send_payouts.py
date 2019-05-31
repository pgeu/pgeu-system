# Send payouts to TransferWise
#
# Copyright (C) 2019, PostgreSQL Europe
#

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.transferwise.models import TransferwiseTransaction, TransferwiseRefund
from postgresqleu.transferwise.models import TansferwisePayout

from datetime import datetime, timedelta
import re


class Command(BaseCommand):
    help = 'Send TransferWise payouts'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=30)
        trigger_next_jobs = 'postgresqleu.transferwise.transferwise_fetch_transactions'

        @classmethod
        def should_run(self):
            return TransferwisePayout.objects.filter(sentat__isnull=True).exists()

    def handle(self, *args, **options):
        for p in TransferwisePayout.objects.filter(sentat__isnull=True):
            self.handle_one_payout(p)

    @transaction.atomic
    def handle_one_payout(self, p):
        method = p.paymentmethod
        pm = method.get_implementation()

        api = pm.get_api()

        (p.accid, p.quoteid, p.transferid) = api.make_transfer(
            p.counterpart_name,
            p.counterpart_account,
            p.amount,
            p.reference,
            p.uuid
        )
        p.sentat = datetime.now()
        p.save()
