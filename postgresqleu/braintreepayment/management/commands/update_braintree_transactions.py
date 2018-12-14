#!/usr/bin/env python
#
# Process transaction statuses from Braintree. They don't send notifications when a
# transaction is settled, but they do have a poll-based API.
#
# Copyright (C) 2015-2016, PostgreSQL Europe
#

import logging
from datetime import date, datetime, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.conf import settings

import braintree

from postgresqleu.braintreepayment.models import BraintreeTransaction, BraintreeLog
from postgresqleu.braintreepayment.util import initialize_braintree
from postgresqleu.accounting.util import create_accounting_entry

# We need to filter the log messages since libraries used by the
# braintree integration spit out debugging information as INFO.
class LogFilter(object):
    def filter(self, record):
        if record.levelno == logging.INFO and record.msg.startswith("Starting new HTTPS connection"):
            return 0
        return 1


class Command(BaseCommand):
    help = 'Process Braintree transaction statuses'

    def handle(self, *args, **options):
        logging.getLogger('urllib3.connectionpool').addFilter(LogFilter())
        initialize_braintree()

        with transaction.atomic():
            for t in BraintreeTransaction.objects.filter(Q(settledat__isnull=True) | Q(disbursedat__isnull=True)):
                # Process all transactions that are not settled and disbursed
                try:
                    btrans = braintree.Transaction.find(t.transid)
                except braintree.exceptions.not_found_error.NotFoundError, ex:
                    BraintreeLog(transid=t.transid,
                                 error=True,
                                 message='Could not find transaction {0}: {1}'.format(t.transid, ex)).save()
                    continue

                if btrans.status == 'settled':
                    # This transaction has now been settled! Yay!
                    # Note that this is the same status we get if it's just
                    # settled, or also disbursed. So we need to compare that
                    # with what's in our db.

                    if not t.settledat:
                        # This transaction has not been recorded as settled, but
                        # it is now. So we mark the settlement.
                        # Braintree don't give us the date/time for the settlement,
                        # so just use whenever we noticed it.
                        t.settledat = datetime.now()
                        t.save()
                        BraintreeLog(transid=t.transid,
                                     message='Transaction has been settled').save()

                        # Create an accounting row. Braintree won't tell us the
                        # fee, and thus the actual settled amount, until after
                        # the money has been disbursed. So assume everything
                        # for now.
                        accstr = "Braintree settlement {0}".format(t.transid)
                        accrows = [
                            (settings.ACCOUNTING_BRAINTREE_AUTHORIZED_ACCOUNT, accstr, -t.amount, None),
                            (settings.ACCOUNTING_BRAINTREE_PAYABLE_ACCOUNT, accstr, t.amount, None),
                        ]
                        create_accounting_entry(date.today(), accrows, False)

                    if t.settledat and not t.disbursedat:
                        # Settled but not disbursed yet. But maybe it is now?
                        if btrans.disbursement_details.success:
                            if btrans.disbursement_details.settlement_currency_iso_code != settings.CURRENCY_ISO:
                                BraintreeLog(transid=t.transid,
                                             error=True,
                                             message='Transaction was disbursed in {0}, should be {1}!'.format(btrans.disbursement_details.settlement_currency_iso_code, settings.CURRENCY_ISO)).save()
                                # No need to send an immediate email on this, we
                                # can deal with it in the nightly batch.
                                continue

                            BraintreeLog(transid=t.transid,
                                         message='Transaction has been disbursed, amount {0}, settled amount {1}'.format(btrans.amount,btrans.disbursement_details.settlement_amount)).save()

                            t.disbursedat = btrans.disbursement_details.disbursement_date
                            t.disbursedamount = btrans.disbursement_details.settlement_amount
                            t.save()

                            # Create an accounting row
                            accstr = "Braintree disbursement {0}".format(t.transid)
                            accrows = [
                                (settings.ACCOUNTING_BRAINTREE_PAYABLE_ACCOUNT, accstr, -t.amount, None),
                                (settings.ACCOUNTING_BRAINTREE_PAYOUT_ACCOUNT, accstr, t.disbursedamount, None),
                            ]
                            if t.amount - t.disbursedamount > 0:
                                accrows.append((settings.ACCOUNTING_BRAINTREE_FEE_ACCOUNT, accstr, t.amount - t.disbursedamount, t.accounting_object))

                            create_accounting_entry(date.today(), accrows, False)
                        elif datetime.today() - t.settledat > timedelta(days=10):
                            BraintreeLog(transid=t.transid,
                                         error=True,
                                         messagE='Transaction {0} was authorized on {1} and settled on {2}, but has not been disbursed yet!'.format(t.transid, t.authorizedat, t.settledat)).save()

                elif datetime.today() - t.authorizedat > timedelta(days=10):
                    BraintreeLog(transid=t.transid,
                                 error=True,
                                 message='Transaction {0} was authorized on {1}, more than 10 days ago, and has not been settled yet!'.format(t.transid, t.authorizedat)).save()

                    # Else just not settled yet, so we'll wait
