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
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

from datetime import datetime
import ConfigParser

from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.accounting.util import create_accounting_entry
from postgresqleu.paypal.models import TransactionInfo, ErrorLog

class Command(BaseCommand):
	help = 'Match pending paypal payments'

	@transaction.atomic
	def handle(self, *args, **options):
		invoicemanager = InvoiceManager()

		translist = TransactionInfo.objects.filter(matched=False).order_by('timestamp')

		for trans in translist:
			# URLs for linkback to paypal
			urls = ["https://www.paypal.com/cgi-bin/webscr?cmd=_view-a-trans&id=%s" % trans.paypaltransid,]

			# Manual handling of some record types

			# Record type: donation
			if trans.transtext == "PostgreSQL Europe donation":
				trans.setmatched('Donation, automatically matched by script')

				# Generate a simple accounting record, that will have to be
				# manually completed.
				accstr = "Paypal donation %s" % trans.paypaltransid
				accrows = [
					(settings.ACCOUNTING_PAYPAL_INCOME_ACCOUNT, accstr, trans.amount-trans.fee, None),
					(settings.ACCOUNTING_PAYPAL_FEE_ACCOUNT, accstr, trans.fee, None),
					(settings.ACCOUNTING_DONATIONS_ACCOUNT, accstr, -trans.amount, None),
					]
				create_accounting_entry(trans.timestamp.date(), accrows, True, urls)
				continue
			# Record type: transfer
			if trans.amount < 0 and trans.transtext == 'Transfer from Paypal to bank':
				trans.setmatched('Bank transfer, automatically matched by script')
				# There are no fees on the transfer, and the amount is already
				# "reversed" and will automatically become a credit entry.
				accstr = 'Transfer from Paypal to bank'
				accrows = [
					(settings.ACCOUNTING_PAYPAL_INCOME_ACCOUNT, accstr, trans.amount, None),
					(settings.ACCOUNTING_PAYPAL_TRANSFER_ACCOUNT, accstr, -trans.amount, None),
					]
				create_accounting_entry(trans.timestamp.date(), accrows, True, urls)
				continue
			# Record type: payment (or refund)
			if trans.amount < 0:
				trans.setmatched('Payment or refund, automatically matched by script')
				# Refunds typically have a fee (a reversed fee), whereas pure
				# payments don't have one. We don't make a difference of them
				# though - we leave the record open for manual verification
				accrows = [
					(settings.ACCOUNTING_PAYPAL_INCOME_ACCOUNT, trans.transtext, trans.amount - trans.fee, None),
				]
				if trans.fee <> 0:
					accrows.append((settings.ACCOUNTING_PAYPAL_FEE_ACCOUNT, trans.transtext, trans.fee, None),)
				create_accounting_entry(trans.timestamp.date(), accrows, True, urls)
				continue

			# Otherwise, it's an incoming payment. In this case, we try to
			# match it to an invoice.

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
				trans.setmatched('Matched standard invoice')
			else:
				# Logging is done by the invoice manager callback
				pass
