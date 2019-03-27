# Fetch transaction list from TransferWise
#
# Copyright (C) 2019, PostgreSQL Europe
#

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

from postgresqleu.invoices.util import InvoiceManager, register_bank_transaction
from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.transferwise.models import TransferwiseTransaction, TransferwiseRefund

from datetime import datetime, timedelta
import re


class Command(BaseCommand):
    help = 'Fetch TransferWise transactions'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=60)

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.transferwise.Transferwise').exists()

    @transaction.atomic
    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.transferwise.Transferwise'):
            self.handle_method(method)

    def handle_method(self, method):
        pm = method.get_implementation()

        api = pm.get_api()

        for t in api.get_transactions():
            # We will re-fetch most transactions, so only create them if they are not
            # already there.
            trans, created = TransferwiseTransaction.objects.get_or_create(
                paymentmethod=method,
                twreference=t['referenceNumber'],
                defaults={
                    'datetime': api.parse_datetime(t['date']),
                    'amount': api.get_structured_amount(t['amount']),
                    'feeamount': api.get_structured_amount(t['totalFees']),
                    'transtype': t['details']['type'],
                    'paymentref': t['details']['paymentReference'],
                    'fulldescription': t['details']['description'],
                }
            )
            if created:
                # Set optional fields
                trans.counterpart_name = t['details'].get('senderName', '')
                trans.counterpart_account = t['details'].get('senderAccount', '').replace(' ', '')
                if trans.counterpart_account:
                    # If account is IBAN, then try to validate it!
                    trans.counterpart_valid_iban = api.validate_iban(trans.counterpart_account)
                trans.save()

                # If this is a refund transaction, process it as such
                if trans.transtype == 'TRANSFER' and trans.paymentref.startswith('{0} refund'.format(settings.ORG_SHORTNAME)):
                    # Yes, this is one of our refunds. Can we find the corresponding transaction?
                    m = re.match('^TRANSFER-(\d+)$', t['referenceNumber'])
                    if not m:
                        raise Exception("Could not find TRANSFER info in transfer reference {0}".format(t['referenceNumber']))
                    transferid = m.groups(1)[0]
                    try:
                        twrefund = TransferwiseRefund.objects.get(transferid=transferid)
                    except TransferwiseRefund.DoesNotExist:
                        print("Could not find transferwise refund for id {0}, registering as manual bank transaction".format(transferid))
                        register_bank_transaction(method, trans.id, trans.amount, trans.paymentref, trans.fulldescription)
                        continue

                    if twrefund.refundtransaction or twrefund.completedat:
                        raise Exception("Transferwise refund for id {0} has already been processed!".format(transferid))

                    # Flag this one as done!
                    twrefund.refundtransaction = trans
                    twrefund.completedat = datetime.now()
                    twrefund.save()

                    invoicemanager = InvoiceManager()
                    invoicemanager.complete_refund(
                        twrefund.refundid,
                        trans.amount + trans.feeamount,
                        trans.feeamount,
                        pm.config('bankaccount'),
                        pm.config('feeaccount'),
                        [],  # urls
                        method,
                    )

                else:
                    # Else register a pending bank transaction. This may immediately match an invoice
                    # if it was an invoice payment, in which case the entire process will copmlete.
                    register_bank_transaction(method, trans.id, trans.amount, trans.paymentref, trans.fulldescription)
