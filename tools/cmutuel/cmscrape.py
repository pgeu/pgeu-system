#!/usr/bin/env python
#
# Scrape the CM pages to fetch list of transactions
#
#
# Copyright (C) 2014, PostgreSQL Europe
#

import pycurl
import cStringIO
import urllib
import datetime
import csv
import sys
import os
from decimal import Decimal
from HTMLParser import HTMLParser


# Set up to run in django environment
from django.core.management import setup_environ
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../postgresqleu'))
import settings
setup_environ(settings)


from django.db import connection, transaction
from django.db.models import Max

from postgresqleu.mailqueue.util import send_simple_mail

from postgresqleu.cmutuel.models import CMutuelTransaction

class FormHtmlParser(HTMLParser):
	def __init__(self):
		HTMLParser.__init__(self)
		self.in_form = False
		self.target_url = None

	def handle_starttag(self, tag, attrs):
		if tag == 'form':
			for k,v in attrs:
				if k == 'action':
					if v.find('telechargement.cgi?'):
						self.in_form = True
						self.target_url = v
						return

class CurlWrapper(object):
	def __init__(self):
		self.curl = pycurl.Curl()
		self.curl.setopt(pycurl.COOKIEFILE, '')

	def request(self, url, post, postdict=None):
		self.curl.setopt(pycurl.URL, str(url))
		readstr = cStringIO.StringIO()
		self.curl.setopt(pycurl.WRITEFUNCTION, readstr.write)
		self.curl.setopt(pycurl.FOLLOWLOCATION, 0)
		if post:
			self.curl.setopt(pycurl.POST, 1)
			curlstr = urllib.urlencode(postdict)
			self.curl.setopt(pycurl.POSTFIELDS, curlstr)
			self.curl.setopt(pycurl.POSTFIELDSIZE, len(curlstr))
		else:
			self.curl.setopt(pycurl.POST, 0)
		self.curl.perform()
		return (self.curl, readstr)

	def get(self, url):
		return self.request(url, False)

	def post(self, url, postdict):
		return self.request(url, True, postdict)


if __name__ == "__main__":
	if not settings.CM_USER_ACCOUNT:
		print "Must specify CM user account in local_settings.py!"
		sys.exit(1)

	verbose=True
	if len(sys.argv) >= 2 and sys.argv[1] in ('-q', '-Q'):
		verbose=False

	curl = CurlWrapper()

	if verbose: print "Logging in..."
	(c,s) = curl.post("https://www.creditmutuel.fr/cmcee/en/identification/default.cgi",
			  {
				  '_cm_app': 'SITFIN',
				  '_cm_idtype': '',
				  '_cm_langue': 'en',
				  '_cm_user': settings.CM_USER_ACCOUNT,
				  '_cm_pwd': settings.CM_USER_PASSWORD,
			  })
	if c.getinfo(pycurl.RESPONSE_CODE) != 302:
		raise Exception("Supposed to receive 302, got %s" % c.getinfo(c.RESPONSE_CODE))
	if c.getinfo(pycurl.REDIRECT_URL) != 'https://www.creditmutuel.fr/cmidf/en/banque/situation_financiere.cgi':
		raise Exception("Received unexpected redirect to '%s'" % c.getinfo(pycurl.REDIRECT_URL))

	# Go to the "situation financiere" to pick up more cookies (SessionStart and SessionTimeout)
	(c,s) = curl.get('https://www.creditmutuel.fr/cmidf/en/banque/situation_financiere.cgi')
	if c.getinfo(pycurl.RESPONSE_CODE) != 302:
		raise Exception("Supposed to receive 302, got %s" % c.getinfo(c.RESPONSE_CODE))
	if c.getinfo(pycurl.REDIRECT_URL) != 'https://www.creditmutuel.fr/cmidf/en/banque/situation_financiere.cgi':
		raise Exception("Received unexpected redirect to '%s'" % c.getinfo(pycurl.REDIRECT_URL))

	# Download the form
	if verbose: print "Downloading form..."
	(c,s) = curl.get('https://www.creditmutuel.fr/cmidf/en/banque/compte/telechargement.cgi')
	if c.getinfo(pycurl.RESPONSE_CODE) != 200:
		raise Exception("Supposed to receive 200, got %s" % c.getinfo(c.RESPONSE_CODE))

	if verbose: print "Parsing form..."
	parser = FormHtmlParser()
	parser.feed(s.getvalue())

	fromdate = CMutuelTransaction.objects.all().aggregate(max=Max('opdate'))
	if fromdate['max']:
		# Overlap with 1 week, just in case there are some old xacts. Yes, we might loose some,
		# but we don't really care :)
		fromdate = fromdate['max']-datetime.timedelta(days=7)
	else:
		# No previous one, so just pick a date... This will only happen once..
		fromdate = datetime.date(2014,1,1)

	if verbose: print "Fetch report since %s" % fromdate
	(c,s) = curl.post("https://www.creditmutuel.fr%s" % parser.target_url, {
		'data_formats_selected':'csv',
		'data_formats_options_cmi_download':'0',
		'data_formats_options_ofx_format':'7',
		'Bool:data_formats_options_ofx_zonetiers':'false',
		'CB:data_formats_options_ofx_zonetiers':'on',
		'data_formats_options_qif_fileformat':'6',
		'ata_formats_options_qif_dateformat':'0',
		'data_formats_options_qif_amountformat':'0',
		'data_formats_options_qif_headerformat':'0',
		'Bool:data_formats_options_qif_zonetiers':'false',
		'CB:data_formats_options_qif_zonetiers':'on',
		'data_formats_options_csv_fileformat':'2',
		'data_formats_options_csv_dateformat':'0',
		'data_formats_options_csv_fieldseparator':'0',
		'data_formats_options_csv_amountcolnumber':'0',
		'data_formats_options_csv_decimalseparator':'1',
		'Bool:data_accounts_account_ischecked':'false',
		'CB:data_accounts_account_ischecked':'on',
		'data_daterange_value':'range',
		'[t:dbt%3adate;]data_daterange_startdate_value':fromdate.strftime('%d/%m/%Y'),
		'[t:dbt%3adate;]data_daterange_enddate_value':'',
		'_FID_DoDownload.x':'57',
		'_FID_DoDownload.y':'17',
		'data_accounts_selection':'1',
		'data_formats_options_cmi_show':'True',
		'data_formats_options_qif_show':'True',
		'data_formats_options_excel_show':'True',
		'data_formats_options_csv_show':'True',
	})
	if c.getinfo(pycurl.RESPONSE_CODE) != 200:
		raise Exception("Supposed to receive 200, got %s" % c.getinfo(c.RESPONSE_CODE))
	with open('csv.csv', 'w') as f:
		f.write(s.getvalue())
	reader = csv.reader(s.getvalue().splitlines(), delimiter=';')

	# Write everything to the database
	with transaction.commit_on_success():
		for row in reader:
			if row[0] == 'Operation date':
				# This is just a header
				continue
			try:
				opdate = datetime.datetime.strptime(row[0], '%d/%m/%Y')
				valdate = datetime.datetime.strptime(row[1], '%d/%m/%Y')
				amount = Decimal(row[2])
				description = row[3]
				balance = Decimal(row[4])

				if not CMutuelTransaction.objects.filter(opdate=opdate, valdate=valdate, amount=amount, description=description).exists():
					CMutuelTransaction(opdate=opdate,
									   valdate=valdate,
									   amount=amount,
									   description=description,
									   balance=balance).save()
			except Exception, e:
				print "Exception '%s' when parsing row %s" % (e, row)

	# Now send things off if there is anything to send
	with transaction.commit_on_success():
		if CMutuelTransaction.objects.filter(sent=False).exists():
			sio = cStringIO.StringIO()
			sio.write("One or more new transactions have been recorded in the Credit Mutuel account:\n\n")
			sio.write("%-10s  %15s  %s\n" % ('Date', 'Amount', 'Description'))
			sio.write("-" * 50)
			sio.write("\n")
			for cmt in CMutuelTransaction.objects.filter(sent=False).order_by('opdate'):
				# Maybe this shouldn't be hardcoded, but for now it is.
				# Exclude Adyen transactions, since they are already reported separately.
				# Still flag them as sent though, so they don't queue up forever.
				if not cmt.description.startswith('VIR STG ADYEN '):
					sio.write("%10s  %15s  %s\n" % (cmt.opdate, cmt.amount, cmt.description))

				cmt.sent = True
				cmt.save()
			send_simple_mail(settings.INVOICE_SENDER_EMAIL,
							 settings.INVOICE_SENDER_EMAIL,
							 'New Credit Mutuel transactions',
							 sio.getvalue())

	connection.close()
