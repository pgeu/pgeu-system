#!/usr/bin/env python
#
# This script downloads all paypal transaction data from one or more accounts,
# and stores them in the database for further processing. No attempt is made
# to match the payment to something elsewhere in the system - that is handled
# by separate scripts.
#
# Copyright (C) 2010-2016, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.db import transaction, connection
from django.conf import settings

from datetime import datetime, timedelta
from decimal import Decimal

from postgresqleu.paypal.models import TransactionInfo
from postgresqleu.paypal.util import PaypalAPI


class PaypalBaseTransaction(object):
    def __init__(self, apistruct):
        self.message = None

        self.transinfo = TransactionInfo(
            paypaltransid=apistruct['TRANSACTIONID'],
            sourceaccount_id=settings.PAYPAL_DEFAULT_SOURCEACCOUNT,
        )
        try:
            self.transinfo.timestamp = datetime.strptime(apistruct['TIMESTAMP'], '%Y-%m-%dT%H:%M:%SZ')
            self.transinfo.amount = Decimal(apistruct['AMT'])
            self.transinfo.fee = -Decimal(apistruct['FEEAMT'])
            self.transinfo.sendername = apistruct['NAME']
        except Exception as e:
            self.message = "Unable to parse: %s" % e

    def __str__(self):
        if self.message:
            return self.message
        return str(self.transinfo)

    def already_processed(self):
        return TransactionInfo.objects.filter(paypaltransid=self.transinfo.paypaltransid).exists()

    def fetch_details(self, api):
        r = api.get_transaction_details(self.transinfo.paypaltransid)
        if r['TRANSACTIONTYPE'][0] == 'cart':
            # Always retrieve the first item in the cart
            # XXX: does this always come back in the same order as sent?
            # So far, all testing indicates it does
            self.transinfo.transtext = r['L_NAME0'][0]
        elif r['TRANSACTIONTYPE'][0] == 'sendmoney':
            # This is sending of money, and not receiving. The transaction
            # text (naturally) goes in a completely different field.
            if 'NOTE' in r:
                self.transinfo.transtext = 'Paypal payment: %s' % r['NOTE'][0]
            else:
                self.transinfo.transtext = 'Paypal payment with empty note'
        else:
            if 'SUBJECT' in r:
                self.transinfo.transtext = r['SUBJECT'][0]
            elif 'L_NAME0' in r:
                self.transinfo.transtext = r['L_NAME0'][0]
            else:
                self.transinfo.transtext = ""

        if r['L_CURRENCYCODE0'][0] != settings.CURRENCY_ISO:
            self.message = "Invalid currency %s" % r['L_CURRENCYCODE0'][0]
            self.transinfo.transtext += ' (currency %s, manually adjust amount!)' % r['L_CURRENCYCODE0'][0]
            self.transinfo.amount = -1  # just to be on the safe side

    def store(self):
        self.transinfo.matched = False
        self.transinfo.matachinfo = self.message
        self.transinfo.save()


class PaypalTransaction(PaypalBaseTransaction):
    def __init__(self, apistruct):
        super(PaypalTransaction, self).__init__(apistruct)
        try:
            self.transinfo.sender = apistruct['EMAIL']
        except Exception as e:
            self.message = "Unable to parse: %s" % e


class PaypalRefund(PaypalTransaction):
    def fetch_details(self, api):
        super(PaypalRefund, self).fetch_details(api)
        if self.transinfo.transtext:
            self.transinfo.transtext = "Refund of %s" % self.transinfo.transtext
        else:
            self.transinfo.transtext = "Refund of unknown transaction"


class PaypalTransfer(PaypalBaseTransaction):
    def __init__(self, apistruct):
        super(PaypalTransfer, self).__init__(apistruct)
        self.transinfo.transtext = "Transfer from Paypal to bank"
        self.transinfo.fee = 0
        self.transinfo.sender = 'treasurer@postgresql.eu'
        if apistruct.get('CURRENCYCODE', None) != settings.CURRENCY_ISO:
            self.message = "Invalid currency %s" % apistruct['CURRENCYCODE']
            self.transinfo.transtext += ' (currency %s, manually adjust amount!)' % apistruct['CURRENCYCODE']
            self.transinfo.amount = -1  # To be on the safe side

    def fetch_details(self, api):
        # We cannot fetch more details, but we also don't need more details..
        pass


class Command(BaseCommand):
    help = 'Fetch updated list of transactions from paypal'

    @transaction.atomic
    def handle(self, *args, **options):
        synctime = datetime.now()
        api = PaypalAPI()

        cursor = connection.cursor()
        cursor.execute("SELECT lastsync FROM paypal_sourceaccount WHERE id=%(id)s", {
            'id': settings.PAYPAL_DEFAULT_SOURCEACCOUNT,
        })

        # Fetch all transactions from last sync, with a 3 day overlap
        for r in api.get_transaction_list(cursor.fetchall()[0][0] - timedelta(days=3)):
            if r['TYPE'] in ('Payment', 'Donation', 'Purchase'):
                t = PaypalTransaction(r)
            elif r['TYPE'] in ('Transfer'):
                t = PaypalTransfer(r)
            elif r['TYPE'] in ('Refund'):
                t = PaypalRefund(r)
            elif r['TYPE'] in ('Fee Reversal'):
                # These can be ignored since they also show up on the
                # actual refund notice.
                continue
            elif r['TYPE'] in ('Currency Conversion (credit)', 'Currency Conversion (debit)'):
                # Cross-currency payments generates multiple entries, but
                # we're only interested in the main one.
                continue
            elif r['TYPE'] in ('Temporary Hold', 'Authorization'):
                # Temporary holds and authorizations are ignored, they will
                # get re-reported once the actual payment clears.
                continue
            else:
                self.stderr.write("Don't know what to do with paypal transaction of type {0}".format(r['TYPE']))
                continue

            if t.already_processed():
                continue
            t.fetch_details(api)
            t.store()

        # Update the sync timestamp
        cursor.execute("UPDATE paypal_sourceaccount SET lastsync=%(st)s WHERE id=%(id)s", {
            'st': synctime,
            'id': settings.PAYPAL_DEFAULT_SOURCEACCOUNT,
        })
