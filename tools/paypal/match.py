#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This is a very trivial match runner for paypal, which just calls into
# the main invoice system to match payments.
#
# A previous version of the script used to do a lot more elaborate matching,
# but all that logic is now folded into the main invoicing system.
#
# We still maintain paypal-specific state in the database though.
#
# Copyright (C) 2010-2013, PostgreSQL Europe
#

from datetime import datetime, timedelta, date
import re
import os
import sys
import ConfigParser

# Set up to run in django environment
from django.core.management import setup_environ
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../postgresqleu'))
import settings
setup_environ(settings)

from django.db import connection, transaction

from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.accounting.util import create_accounting_entry
from postgresqleu.paypal.models import *

# Read our local settings too
cfg = ConfigParser.ConfigParser()
cfg.read('paypal.ini')

@transaction.commit_on_success
def run():
	invoicemanager = InvoiceManager()

	translist = TransactionInfo.objects.filter(matched=False).order_by('id')

	for trans in translist:
		# URLs for linkback to paypal
		urls = ["https://www.paypal.com/cgi-bin/webscr?cmd=_view-a-trans&id=%s" % ti.paypaltransid,]
		# If this is a donation, match it manually
		if trans.transtext == "PostgreSQL Europe donation":
			trans.matched = True
			trans.matchinfo = 'Donation, automatically matched by script'
			trans.save()

			# Generate a simple accounting record, that will have to be
			# manually completed.
			accstr = "Paypal donation %s" % ti.paypaltransid
			accrows = [
				(settings.ACCOUNTING_PAYPAL_INCOME_ACCOUNT, accstr, ti.amount-ti.fee),
				(settings.ACCOUNTING_PAYPAL_FEE_ACCOUNT, accstr, ti.fee),
				(settings.ACCOUNTING_DONATIONS_ACCOUNT, accstr, -ti.amount),
				]
			create_accounting_entry(date.today(), accrows, True, urls)
			continue

		# Log things to the db
		def payment_logger(msg):
			# Write the log output to somewhere interesting!
			ErrorLog(timestamp=datetime.now(),
					 sent=False,
					 message='Paypal %s by %s (%s) on %s: %s' % (
					trans.paypaltransid,
					trans.sender,
					trans.sendername,
					trans.timestamp,
					msg
					)).save()

		(r,i,p) = invoicemanager.process_incoming_payment(trans.transtext,
														  trans.amount,
														  "Paypal id %s, from %s <%s>" % (trans.paypaltransid, trans.sendername, trans.sender),
														  trans.fee,
														  settings.ACCOUNTING_PAYPAL_INCOME_ACCOUNT,
														  settings.ACCOUNTING_PAYPAL_FEE_ACCOUNT,
														  urls,
														  payment_logger)

		if r == invoicemanager.RESULT_OK:
			trans.matched = True
			trans.matchinfo = 'Matched standard invoice'
			trans.save()
		else:
			# Logging is done by the invoice manager callback
			pass

if __name__ == "__main__":
	run()
	connection.close()
