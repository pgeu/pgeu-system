# Fetch transaction list from Qonto
#
# Copyright (C) 2026, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date, parse_datetime
from django.db import transaction
from django.conf import settings

from postgresqleu.invoices.util import register_bank_transaction
from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.qonto.models import QontoTransaction

from datetime import datetime, time
from decimal import Decimal


class Command(BaseCommand):
    help = 'Fetch Qonto transactions'

    class ScheduledJob:
        scheduled_times = [
            time(9, 30),
            time(13, 30),
            time(18, 30),
        ]

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.qonto.Qonto').exists()

    def add_arguments(self, parser):
        parser.add_argument('--no-banktransactions', action='store_true', help="Don't create banktransaction entries for found records (useful for initial load)")

    @transaction.atomic
    def handle(self, *args, **options):
        self.do_banktransactions = not options['no_banktransactions']

        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.qonto.Qonto'):
            self.handle_method(method)

    def handle_method(self, method):
        impl = method.get_implementation()

        for t in impl.fetch_transactions():
            trans, created = QontoTransaction.objects.get_or_create(
                paymentmethod=method,
                qontoid=t['id'],
                defaults={
                    'datetime': datetime.fromisoformat(t['created_at']),
                    'amount': Decimal(str(t['amount'])) * (-1 if t['side'] == 'debit' else 1),
                    'paymentref': self.get_reference_text(t['reference'], t['operation_type'])[:200],
                    'operation_type': t['operation_type'],
                    'counterpart_iban': t['income']['counterparty_account_number'] if t['income'] and t['income'].get('counterparty_account_number_format') == 'IBAN' else '',
                    'counterpart_bic': t['income']['counterparty_bank_identifier'] if t['income'] and t['income'].get('counterparty_bank_identifier_format') == 'SWIFT_BIC' else '',
                }
            )
            if created:
                if method.config.get('notify_each_transaction', False):
                    send_simple_mail(
                        settings.INVOICE_SENDER_EMAIL,
                        method.config['notification_receiver'],
                        "Qonto transaction received on {}".format(method.internaldescription),
                        "A new qonto transaction has been registered for {}:\n\nTime:   {}\nAmount: {}\nText:   {}\n".format(
                            method.internaldescription,
                            trans.datetime,
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

    def get_reference_text(self, reference, optype):
        if optype == 'qonto_fee':
            return 'Qonto fee: {}'.format(reference)
        return reference
