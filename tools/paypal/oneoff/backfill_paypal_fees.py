#!/usr/bin/env python

# Backfill paypal fees into the database, from the dates before
# we were tracking them live.

import os
import sys
import ConfigParser
from decimal import Decimal

sys.path.append('..')
from paypal import PaypalAPI

# Set up to run in django environment
from django.core.management import setup_environ
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../../postgresqleu'))
import settings
setup_environ(settings)

from django.db import transaction

from postgresqleu.paypal.models import TransactionInfo

cfg = ConfigParser.ConfigParser()
cfg.read('../paypal.ini')

if __name__ == "__main__":
    api = PaypalAPI(cfg.get('postgresqleu', 'user'), cfg.get('postgresqleu', 'apipass'), cfg.get('postgresqleu', 'apisig'), 0)

    for ti in TransactionInfo.objects.filter(fee__isnull=True).order_by('timestamp'):
        with transaction.commit_on_success():
            info = api.get_transaction_details(ti.paypaltransid)
            if Decimal(info['AMT'][0]) != ti.amount:
                print "%s: Unmatched amounts. Db has %s, paypal has %s." % (ti.paypaltransid, ti.amount, info['AMT'][0])
                sys.exit(1)
            # Amounts match, get the fee
            # For donations, there is no fee and a different xtype
            if info['TRANSACTIONTYPE'][0] == 'sendmoney' and not info.has_key('FEEAMT'):
                print "%s: Amount %s, donation, no fee" % (ti.paypaltransid, ti.amount)
                ti.fee = 0
            else:
                ti.fee = Decimal(info['FEEAMT'][0])
                print "%s: Amount %s, fee %s (%.2f%%)" % (ti.paypaltransid, ti.amount, ti.fee, 100*ti.fee/ti.amount)
            ti.save()
