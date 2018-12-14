#!/usr/bin/env python

# Backfill accounting records for all paid invoices in the system, as
# well as for all Adyen and Paypal transactions.

# This does some ugly magic to track down payment information for both
# paypal and adyen invoices, to generate accounting entries that look
# like they would if the accounting system had been in place when they
# were paid. This relies on some text fields that we really shouldn't
# rely on, but it's a one-off thing...


import os
import sys
import re
import logging
from datetime import datetime
from pprint import pprint

# Set up to run in django environment
from django.core.management import setup_environ
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../../postgresqleu'))
import settings
setup_environ(settings)

from django.db import transaction

from postgresqleu.invoices.models import Invoice
from postgresqleu.paypal.models import TransactionInfo as PaypalTrans
from postgresqleu.adyen.models import TransactionStatus as AdyenTrans

from postgresqleu.accounting.util import create_accounting_entry

re_paypal = re.compile('^Paypal id (\w+), from')
re_adyen = re.compile('^Adyen id (\d+)$')

if __name__ == "__main__":
    logging.disable(logging.WARNING)
    with transaction.commit_on_success():
        invoices = Invoice.objects.filter(paidat__isnull=False).order_by('paidat')

        paypal_handled = []
        adyen_handled = []
        allentries = []
        for invoice in invoices:
            if invoice.deleted:
                raise Exception("Invoice %s is deleted but paid?!" % invoice.id)
            if invoice.refunded:
                print "Sorry, don't know how to deal with refunded invoice %s" % invoice.id
                continue

            thisentry = {
                'date': invoice.paidat.date(),
                'text': 'Invoice #%s: %s' % (invoice.id, invoice.title),
                'rows': [],
                'leaveopen': False,
            }
            if invoice.accounting_account:
                thisentry['rows'].append(
                    (invoice.accounting_account, -invoice.total_amount, invoice.accounting_object),)
            else:
                # Can't complete this entry
                thisentry['leaveopen'] = True

            # Try to figure out how this invoice is paid
            m = re_paypal.match(invoice.paymentdetails)
            if m:
                ptrans = PaypalTrans.objects.get(paypaltransid=m.groups(1)[0])
                if not ptrans.fee:
                    print "Invoice %s had no paypal fee, that can't be right!" % invoice.id
                    continue
                thisentry['rows'].extend([
                    (settings.ACCOUNTING_PAYPAL_FEE_ACCOUNT, ptrans.fee, invoice.accounting_object),
                    (settings.ACCOUNTING_PAYPAL_INCOME_ACCOUNT, invoice.total_amount - ptrans.fee, None),
                    ])
                allentries.append(thisentry)
                paypal_handled.append(ptrans.id)
                continue
            m = re_adyen.match(invoice.paymentdetails)
            if m:
                atrans = AdyenTrans.objects.get(pspReference=m.groups(1)[0])
                if not atrans.settledat:
                    print "Invoice %s paid by adyen %s has not been settled yet!" % (invoice.id, atrans.id)
                    continue

                # Since we found it, let's correct the accounting object
                # if it's not there yet.
                if atrans.accounting_object != invoice.accounting_object:
                    atrans.accounting_object = invoice.accounting_object
                    atrans.save()

                thisentry['rows'].append(
                    (settings.ACCOUNTING_ADYEN_AUTHORIZED_ACCOUNT, invoice.total_amount, None),)
                allentries.append(thisentry)

                # Add a separate entry for the settlement
                allentries.append({
                    'date': atrans.settledat.date(),
                    'text': 'Adyen settlement %s' % atrans.pspReference,
                    'rows': [
                        (settings.ACCOUNTING_ADYEN_AUTHORIZED_ACCOUNT, -atrans.amount, None),
                        (settings.ACCOUNTING_ADYEN_PAYABLE_ACCOUNT, atrans.settledamount, None),
                        (settings.ACCOUNTING_ADYEN_FEE_ACCOUNT, atrans.amount - atrans.settledamount, atrans.accounting_object),
                        ],
                    'leaveopen': False})

                adyen_handled.append(atrans.id)
                continue
            # This is a manually paid invoice, so we're going to assume
            # it was paid by bank xfer.
            thisentry['rows'].append(
                (settings.ACCOUNTING_MANUAL_INCOME_ACCOUNT, invoice.total_amount, None),)
            allentries.append(thisentry)

        # Find all other paypal transactions
        for ptrans in PaypalTrans.objects.filter(timestamp__gt=datetime(2013, 01, 01, 0, 0, 0)).exclude(id__in=paypal_handled):
            if not ptrans.fee:
                print "Paypal %s has no paypal fee, that can't be right!" % ptrans.id
                continue
            allentries.append({
                'date': ptrans.timestamp.date(),
                'text': 'Paypal %s - %s - update manually' % (ptrans.paypaltransid, ptrans.transtext),
                'rows': [
                    (settings.ACCOUNTING_PAYPAL_FEE_ACCOUNT, ptrans.fee, None),
                    (settings.ACCOUNTING_PAYPAL_INCOME_ACCOUNT, ptrans.amount - ptrans.fee, None),
                    ],
                'leaveopen': True,
                })

        # Find all other adyen transactoins
        for atrans in AdyenTrans.objects.filter(authorizedat__gt=datetime(2013, 01, 01, 0, 0, 0), settledat__isnull=False).exclude(id__in=adyen_handled):
            if atrans.amount == 0:
                print "Adyen transaction %s rounded off to 0, deal with manually!" % atrans.pspReference
                continue
            allentries.append({
                'date': atrans.authorizedat.date(),
                'text': 'Adyen %s - %s - update manually' % (atrans.pspReference, atrans.notification.merchantReference),
                'rows': [
                    (settings.ACCOUNTING_ADYEN_AUTHORIZED_ACCOUNT, atrans.amount, None),
                    ],
                'leaveopen': True,
                })
            allentries.append({
                'date': atrans.settledat.date(),
                'text': 'Adyen settlement %s' % atrans.pspReference,
                'rows': [
                    (settings.ACCOUNTING_ADYEN_AUTHORIZED_ACCOUNT, -atrans.amount, None),
                    (settings.ACCOUNTING_ADYEN_PAYABLE_ACCOUNT, atrans.settledamount, None),
                    (settings.ACCOUNTING_ADYEN_FEE_ACCOUNT, atrans.amount - atrans.settledamount, None),
                ],
                'leaveopen': False,
            })

        allentries.sort(key=lambda e: e['date'])

        # Now is when we create the actual records...
        for entry in allentries:
            try:
                create_accounting_entry(
                    entry['date'],
                    [(r[0], entry['text'], r[1], r[2]) for r in entry['rows']],
                    entry['leaveopen'])
            except:
                print "Failed on this entry:"
                pprint(entry)
                raise
        print "Created %s entries" % len(allentries)

        while True:
            if raw_input("Does this seem reasonable? Type 'yes' to commit, or hit ctrl-c to abort. So? ") == 'yes':
                break
    print "All done!"
