#!/usr/bin/env python

# Backfill account_number and account_object on invoices where possible,
# based on conference invoices and membership invoices.
#
# There's some ugly hardcoded magic in there, but that doesn't really
# matter since it's a one-off script..


import os
import sys
import logging

# Set up to run in django environment
from django.core.management import setup_environ
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../../postgresqleu'))
import settings
setup_environ(settings)

from django.db import transaction

from postgresqleu.invoices.models import Invoice, InvoiceProcessor
from postgresqleu.confreg.models import ConferenceRegistration, BulkPayment

if __name__ == "__main__":
	logging.disable(logging.WARNING)
	with transaction.commit_on_success():
		invoices = Invoice.objects.filter(paidat__isnull=False, accounting_account__isnull=True).order_by('paidat')

		processor_confreg = InvoiceProcessor.objects.get(processorname='confreg processor')
		processor_bulkreg = InvoiceProcessor.objects.get(processorname='confreg bulk processor')
		processor_membership = InvoiceProcessor.objects.get(processorname='membership processor')

		for invoice in invoices:
			# Try to determine what it is
			if invoice.processor == processor_confreg:
				# This is a conference registration
				invoice.accounting_account = settings.ACCOUNTING_CONFREG_ACCOUNT
				invoice.accounting_object = ConferenceRegistration.objects.get(pk=invoice.processorid).conference.accounting_object
			elif invoice.processor == processor_bulkreg:
				# This is a bulk registration
				invoice.accounting_account = settings.ACCOUNTING_CONFREG_ACCOUNT
				invoice.accounting_object = BulkPayment.objects.get(pk=invoice.processorid).conference.accounting_object
			elif invoice.processor == processor_membership:
				# This is a membership. It has an account, but no object
				invoice.accounting_account = settings.ACCOUNTING_MEMBERSHIP_ACCOUNT
				invoice.accounting_object = None
			else:
				print "Invoice #%s has unknown processor. Enter info manually, plase!" % invoice.id
				while True:
					try:
						invoice.accounting_account = int(raw_input('Enter account number: '))
						break
					except KeyboardInterrupt:
						raise
					except:
						pass
				invoice.accounting_object = raw_input('Enter object name: ')
			print "Invoice %s, account %s, object %s" % (invoice.id, invoice.accounting_account, invoice.accounting_object)
			invoice.save()

		while True:
			if raw_input("Does this seem reasonable? Type 'yes' to commit, or hit ctrl-c to abort. So? ") == 'yes':
				break
	print "All done!"
