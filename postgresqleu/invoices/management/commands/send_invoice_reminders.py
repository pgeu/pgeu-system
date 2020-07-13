# Send invoice reminders.
#
# Copyright (C) 2015, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from datetime import timedelta, time

from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.util import InvoiceWrapper


class Command(BaseCommand):
    help = 'Send invoice reminders'

    class ScheduledJob:
        scheduled_times = [time(8, 18), ]
        internal = True

    @transaction.atomic
    def handle(self, *args, **options):
        # We send reminder automatically when an invoice is 1 day overdue.
        # We never send a second reminder, that is done manually.
        invoices = Invoice.objects.filter(finalized=True, deleted=False, paidat__isnull=True, remindersent__isnull=True, duedate__lt=timezone.now() - timedelta(days=1))
        for invoice in invoices:
            wrapper = InvoiceWrapper(invoice)
            wrapper.email_reminder()
            invoice.remindersent = timezone.now()
            invoice.save()
            self.stdout.write("Sent invoice reminder for #{0} - {1}".format(invoice.id, invoice.title))
