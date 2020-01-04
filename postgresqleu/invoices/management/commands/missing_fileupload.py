#
# Send reminders about bank accounts that have not received uploaded
# files recently.
#
# Copyright (C) 2020 PostgreSQL Europe
#
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from datetime import datetime, timedelta, time

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.invoices.models import BankFileUpload, InvoicePaymentMethod


class Command(BaseCommand):
    help = 'Send reminders about missing bank file uploads'

    class ScheduledJob:
        scheduled_times = [time(7, 35), ]
        internal = True

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, config__has_key='file_upload_interval', config__file_upload_interval__gt=0).exists()

    @transaction.atomic
    def handle(self, *args, **options):
        accounts = []
        for pm in InvoicePaymentMethod.objects.filter(active=True, config__has_key='file_upload_interval', config__file_upload_interval__gt=0):
            if not BankFileUpload.objects.filter(method=pm,
                                                 created__gt=datetime.now() - timedelta(days=pm.config['file_upload_interval'])
            ).exists():
                accounts.append(pm.internaldescription)

        if accounts:
            send_simple_mail(
                settings.INVOICE_SENDER_EMAIL,
                settings.INVOICE_NOTIFICATION_RECEIVER,
                "Bank accounts are missing uploaded files",
                """The following bank accounts have not received an uploaded file within the
configured interval:

* {0}

Uploading can be done at {1}/admin/invoices/bankfiles/
"""
                .format(
                    "\n* ".join(accounts),
                    settings.SITEBASE,
                )
            )
