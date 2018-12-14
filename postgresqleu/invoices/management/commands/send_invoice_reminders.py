# Send invoice reminders.
#
# Copyright (C) 2015, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.db import transaction

from datetime import datetime, timedelta

from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.util import InvoiceWrapper


class Command(BaseCommand):
    help = 'Send invoice reminders'

    @transaction.atomic
    def handle(self, *args, **options):
        # We send reminder automatically when an invoice is 1 day overdue.
        # We never send a second reminder, that is done manually.
        invoices = Invoice.objects.filter(finalized=True, deleted=False, refund__isnull=True, paidat__isnull=True, remindersent__isnull=True, duedate__lt=datetime.now() - timedelta(days=1))
        for invoice in invoices:
            wrapper = InvoiceWrapper(invoice)
            wrapper.email_reminder()
            invoice.remindersent = datetime.now()
            invoice.save()
            self.stdout.write("Sent invoice reminder for #{0} - {1}".format(invoice.id, invoice.title))
