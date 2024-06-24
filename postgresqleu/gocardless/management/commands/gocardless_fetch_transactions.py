# Fetch transaction list from gocardless
#
# Copyright (C) 2024, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.timezone import make_aware
from django.db import transaction
from django.conf import settings

from postgresqleu.invoices.util import register_bank_transaction
from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.gocardless.models import GocardlessTransaction

from datetime import time
from decimal import Decimal


class Command(BaseCommand):
    help = 'Fetch Gocadless transactions'

    class ScheduledJob:
        scheduled_times = [
            time(9, 30),
            time(18, 30),
        ]

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.gocardless.Gocardless').exists()

    def add_arguments(self, parser):
        parser.add_argument('--no-banktransactions', action='store_true', help="Don't create banktransaction entries for found records (useful for initial load)")

    @transaction.atomic
    def handle(self, *args, **options):
        self.do_banktransactions = not options['no_banktransactions']

        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.gocardless.Gocardless'):
            self.handle_method(method)

    def handle_method(self, method):
        impl = method.get_implementation()

        for t in impl.fetch_transactions():
            trans, created = GocardlessTransaction.objects.get_or_create(
                paymentmethod=method,
                transactionid=t['transactionId'],
                defaults={
                    'date': t['bookingDate'],
                    'amount': Decimal(str(t['transactionAmount']['amount'])),
                    'paymentref': ' '.join(t['remittanceInformationUnstructuredArray'])[:200],
                    'transactionobject': t,
                }
            )
            if created:
                if method.config.get('notify_each_transaction', False):
                    send_simple_mail(
                        settings.INVOICE_SENDER_EMAIL,
                        method.config['notification_receiver'],
                        "Gocardless transaction received on {}".format(method.internaldescription),
                        "A new gocardless transaction has been registered for {}:\n\nDate:   {}\nAmount: {}\nText:   {}\n".format(
                            method.internaldescription,
                            trans.date,
                            trans.amount,
                            trans.paymentref,
                        ),
                    )

                # Also register a pending bank transaction. This may immediately match an invoice
                # if it was an invoice payment, in which case the entire process will complete..
                if self.do_banktransactions:
                    register_bank_transaction(
                        method,
                        trans.id,
                        trans.amount,
                        trans.paymentref,
                        trans.paymentref,
                    )
