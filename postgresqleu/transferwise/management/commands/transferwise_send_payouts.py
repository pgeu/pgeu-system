# Send payouts to TransferWise
#
# Copyright (C) 2019, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from postgresqleu.transferwise.models import TransferwisePayout

from datetime import timedelta


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
        p.sentat = timezone.now()
        p.save()
