#!/usr/bin/env python
#
# Process reports from Adyen. This includes downloading them for storage,
# as well as processing the contents.
#
# Copyright (C) 2013, PostgreSQL Europe
#

import os
import sys

# Set up to run in django environment
from django.core.management import setup_environ
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../postgresqleu'))
import settings
setup_environ(settings)

from django.db import transaction, connection

import csv
import urllib2
import StringIO
from base64 import standard_b64encode
from datetime import datetime, date
from decimal import Decimal

from postgresqleu.adyen.models import AdyenLog, Report, TransactionStatus
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.accounting.util import create_accounting_entry


def download_reports():
	# Download all currently pending reports (that we can)
	for report in Report.objects.filter(downloadedat=None).order_by('receivedat'):
		try:
			with transaction.commit_on_success():
				print "Downloading %s" % report.url
				req = urllib2.Request(report.url)
				req.add_header('Authorization', 'Basic %s' % (
					standard_b64encode('%s:%s' % (settings.ADYEN_REPORT_USER, settings.ADYEN_REPORT_PASSWORD)),
					))
				u = urllib2.urlopen(req)
				resp = u.read()
				u.close()
				report.downloadedat = datetime.now()
				report.contents = resp
				report.save()
				AdyenLog(message='Downloaded report %s' % report.url, error=False).save()
		except Exception, ex:
			print >> sys.stderr, "Failed to download report %s: %s" % (report.url, ex)
			AdyenLog(message='Failed to download report %s: %s' % (report.url, ex), error=True).save()




def process_payment_accounting_report(report):
	sio = StringIO.StringIO(report.contents)
	reader = csv.DictReader(sio, delimiter=',')
	for l in reader:
		# SentForSettle is what we call capture, so we track that
		# Settled is when we actually receive the money
		# Everything else we ignore
		if l['Record Type'] == 'SentForSettle' or l['Record Type'] == 'Settled':
			# Find the actual payment
			pspref = l['Psp Reference']
			bookdate = l['Booking Date']
			try:
				trans = TransactionStatus.objects.get(pspReference=pspref)
			except TransactionStatus.DoesNotExist:
				# Yes, for now we rollback the whole processing of this one
				raise Exception('Transaction %s not found!' % pspref)
			if l['Record Type'] == 'SentForSettle':
				# If this is a POS transaction, it typically received a
				# separate CAPTURE notification, in which case the capture
				# date is already set. But if not, we'll set it to the
				# sent for settle date.
				if not trans.capturedat:
					trans.capturedat = bookdate
					trans.method = l['Payment Method']
					trans.save()
					AdyenLog(message='Transaction %s captured at %s' % (pspref, bookdate), error=False).save()
					print "Sent for settle on %s" % pspref
			elif l['Record Type'] == 'Settled':
				if trans.settledat != None:
					raise Exception('Transaction %s settled more than once?!' % pspref)
				trans.settledat = bookdate
				trans.settledamount = Decimal(l['Main Amount'], 2)
				trans.save()
				print "Setteld %s, total amount %s" % (pspref, trans.settledamount)
				AdyenLog(message='Transaction %s settled at %s' % (pspref, bookdate), error=False).save()

				# Settled transactions create a booking entry
				accstr = "Adyen settlement %s" % pspref
				accrows = [
					(settings.ACCOUNTING_ADYEN_AUTHORIZED_ACCOUNT, accstr, -trans.amount, None),
					(settings.ACCOUNTING_ADYEN_PAYABLE_ACCOUNT, accstr, trans.settledamount, None),
					(settings.ACCOUNTING_ADYEN_FEE_ACCOUNT, accstr, trans.amount-trans.settledamount, trans.accounting_object),
					]
				#create_accounting_entry(date.today(), accrows, False)

def process_received_payments_report(report):
	# We don't currently do anything with this report, but we store the contents
	# of them in case we might need them in the future.
	pass

def process_settlement_detail_report_batch(report):
	# Summarize the settlement detail report in an email to to treasurer@, so they
	# can keep track of what's going on.
	sio = StringIO.StringIO(report.contents)
	reader = csv.DictReader(sio, delimiter=',')
	types = {}
	for l in reader:
		t = l['Type']
		lamount = Decimal(l['Net Credit (NC)'] or 0) - Decimal(l['Net Debit (NC)'] or 0)
		if types.has_key(t):
			types[t] += lamount
		else:
			types[t] = lamount

	def sort_types(a):
		# Special sort method that just ensures that Settled always ends up at the top
		# and the rest is just alphabetically sorted. (And yes, this is ugly code :P)
		if a[0] == 'Settled':
			return 'AAA'
		return a[0]

	msg = "\n".join(["%-20s: %s" % (k,v) for k,v in sorted(types.iteritems(), key=sort_types)])
	acct = report.notification.merchantAccountCode
	send_simple_mail(settings.INVOICE_SENDER_EMAIL,
					 settings.ADYEN_NOTIFICATION_RECEIVER,
					 'Adyen settlement batch completed',
					 "An settlement batch with Adyen has completed for merchant account %s. A summary of the entries are:\n\n%s\n" % (acct, msg))


def process_reports():
	# Process all downloaded but unprocessed reports

	for report in Report.objects.filter(downloadedat__isnull = False, processedat=None).order_by('downloadedat'):
		try:
			with transaction.commit_on_success():
				print "Processing %s" % report.url

				# To know what to do, we look at the filename of the report URL
				filename = report.url.split('/')[-1]
				if filename.startswith('payments_accounting_report_'):
					process_payment_accounting_report(report)
				elif filename.startswith('received_payments_report'):
					process_received_payments_report(report)
				elif filename.startswith('settlement_detail_report_batch_'):
					process_settlement_detail_report_batch(report)
				else:
					raise Exception('Unknown report type in file "%s"' % filename)

				# If successful, flag as processed and add the log
				report.processedat = datetime.now()
				report.save()
				AdyenLog(message='Processed report %s' % report.url, error=False).save()
		except Exception, ex:
			print >> sys.stderr, "Failed to process report %s: %s" % (report.url, ex)
			AdyenLog(message='Failed to process report %s: %s' % (report.url, ex), error=True).save()

if __name__ == "__main__":
	usage = "Usage: report_processor.py [-downloadonly|-processonly]\n\n"

	download = process = True
	if len(sys.argv) == 2:
		if sys.argv[1] == '-downloadonly':
			process = False
		elif sys.argv[1] == '-processonly':
			download = False
		else:
			print >> sys.stderr, usage
			exit(1)
	elif len(sys.argv) != 1:
		print >> sys.stderr, usage
		exit(1)

	if download:
		download_reports()
	if process:
		process_reports()
		pass

	connection.close()
