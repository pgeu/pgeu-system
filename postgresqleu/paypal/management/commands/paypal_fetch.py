#!/usr/bin/env python
#
# This script downloads all paypal transaction data from one or more accounts,
# and stores them in the database for further processing. No attempt is made
# to match the payment to something elsewhere in the system - that is handled
# by separate scripts.
#
# Copyright (C) 2010-2019, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from datetime import datetime, timedelta
import dateutil.parser
from decimal import Decimal

from postgresqleu.paypal.models import TransactionInfo
from postgresqleu.paypal.util import PaypalAPI
from postgresqleu.invoices.models import InvoicePaymentMethod


class Command(BaseCommand):
    help = 'Fetch updated list of transactions from paypal'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=30)
        trigger_next_jobs = 'postgresqleu.paypal.paypal_match'

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.paypal.Paypal').exists()

    @transaction.atomic
    def handle(self, *args, **options):
        synctime = timezone.now()

        # There may be multiple accounts, so loop over them
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.paypal.Paypal'):
            try:
                lastsync = method.status['lastsync']
                if isinstance(lastsync, str):
                    lastsync = dateutil.parser.parse(lastsync)
                # Always go back one day to cover for the very slow async update of the
                # Paypal sync api.
                lastsync -= timedelta(days=1)
            except KeyError:
                # Status not set yet, so just assumed we synced a month ago (silly, I know..)
                lastsync = timezone.now() - timedelta(days=31)

            api = PaypalAPI(method.get_implementation())

            # Fetch all transactions from last sync, with a 3 day overlap
            for r in api.get_transaction_list(lastsync - timedelta(days=3)):
                if TransactionInfo.objects.filter(paypaltransid=r['TRANSACTIONID']).exists():
                    continue

                t = TransactionInfo(paypaltransid=r['TRANSACTIONID'])
                t.timestamp = datetime.strptime(r['TIMESTAMP'], '%Y-%m-%dT%H:%M:%S%z')
                t.amount = Decimal(r['AMT'])
                if 'FEEAMT' in r:
                    t.fee = -Decimal(r['FEEAMT'])
                else:
                    t.fee = 0
                t.sender = r['EMAIL']
                t.sendername = r['NAME']
                t.transtext = r['SUBJECT']
                t.matched = False
                t.paymentmethod = method

                t.save()

            # Update the sync timestamp
            method.status['lastsync'] = synctime
            method.save()
