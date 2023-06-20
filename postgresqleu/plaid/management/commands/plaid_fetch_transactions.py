# Fetch transaction list from plaid
#
# Copyright (C) 2023, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.timezone import make_aware
from django.db import transaction
from django.conf import settings

from postgresqleu.invoices.util import register_bank_transaction
from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.plaid.models import PlaidTransaction

from datetime import timedelta, datetime, time
from decimal import Decimal


class Command(BaseCommand):
    help = 'Fetch Plaid transactions'

    class ScheduledJob:
        scheduled_interval = timedelta(hours=12)

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.plaid.Plaid').exists()

    def add_arguments(self, parser):
        parser.add_argument('--no-banktransactions', action='store_true', help="Don't create banktransaction entries for found records (useful for initial load)")

    @transaction.atomic
    def handle(self, *args, **options):
        self.do_banktransactions = not options['no_banktransactions']

        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.plaid.Plaid'):
            self.handle_method(method)

    def handle_method(self, method):
        impl = method.get_implementation()

        for t in impl.sync_transactions():
            # a sync_transactions should normally only get transactions to add, but there is at least a small chance
            # that we can get the same one again, so we dupe-check it.
            trans, created = PlaidTransaction.objects.get_or_create(
                paymentmethod=method,
                transactionid=t['transaction_id'],
                defaults={
                    'datetime': parse_datetime(t['datetime']) if t['datetime'] else make_aware(datetime.combine(parse_date(t['date']), time(0, 0))),
                    'amount': -Decimal(str(t['amount'])),  # All plaid amounts are reported negative
                    'paymentref': t['name'][:200],
                    'transactionobject': t,
                }
            )
            if created:
                if method.config.get('notify_each_transaction', False):
                    send_simple_mail(
                        settings.INVOICE_SENDER_EMAIL,
                        method.config['notification_receiver'],
                        "Plaid transaction received on {}".format(method.internaldescription),
                        "A new plaid transaction has been registered for {}:\n\nDate:   {}\nAmount: {}\nText:   {}\n".format(
                            method.internaldescription,
                            trans.datetime,
                            trans.amount,
                            trans.paymentref,
                        ),
                    )

                # Else register a pending bank transaction. This may immediately match an invoice
                # if it was an invoice payment, in which case the entire process will complete..
                if self.do_banktransactions:
                    register_bank_transaction(
                        method,
                        trans.id,
                        trans.amount,
                        trans.paymentref,
                        trans.paymentref,
                    )
