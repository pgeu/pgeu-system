#
# Send reminders about pending bank transactions that have not been
# processed.
#
# Copyright (C) 2019 PostgreSQL Europe
#
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from datetime import datetime, timedelta, time

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.invoices.models import PendingBankTransaction


class Command(BaseCommand):
    help = 'Send reminders about pending bank transactions'

    class ScheduledJob:
        scheduled_times = [time(7, 30), ]
        internal = True

        @classmethod
        def should_run(self):
            return PendingBankTransaction.objects.filter(created__lte=datetime.now() - timedelta(hours=72)).exists()

    @transaction.atomic
    def handle(self, *args, **options):
        trans = PendingBankTransaction.objects.filter(created__lte=datetime.now() - timedelta(hours=72))
        if trans:
            send_simple_mail(
                settings.INVOICE_SENDER_EMAIL,
                settings.INVOICE_NOTIFICATION_RECEIVER,
                "Pending bank transactions present",
                """There are currently {0} bank transactions that have been pending for more than 24 hours.
This means transactions that were not matched to any invoice or
any expected payout, and thus needs to be processed manually.

{1}

Processing happens at {2}/admin/invoices/banktransactions/
"""
                .format(
                    len(trans),
                    "\n".join(["{0:10f}   {1}".format(t.amount, t.transtext) for t in trans]),
                    settings.SITEBASE)
            )
