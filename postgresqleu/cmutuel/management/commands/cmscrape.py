# Scrape the CM pages to fetch list of transactions
#
#
# Copyright (C) 2014, PostgreSQL Europe
#
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max, Q
from django.conf import settings

import pycurl
import cStringIO
import urllib
import datetime
import csv
import sys
import os
from decimal import Decimal
from HTMLParser import HTMLParser


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

	def expect_redirect(self, fetchpage, redirectto, postdata=None):
		if postdata:
			(c,s) = self.post(fetchpage, postdata)
		else:
			(c,s) = self.get(fetchpage)
		if c.getinfo(pycurl.RESPONSE_CODE) != 302:
			raise CommandError("Supposed to receive 302 for %s, got %s" % (fetchpage, c.getinfo(c.RESPONSE_CODE)))
		if not isinstance(redirectto, list):
			redirrectto = [redirectto, ]
		if not c.getinfo(pycurl.REDIRECT_URL) in redirectto:
			raise CommandError("Received unexpected redirect from %s to '%s' (expected %s)" % (fetchpage, c.getinfo(pycurl.REDIRECT_URL), redirectto))
		return c.getinfo(pycurl.REDIRECT_URL)


class Command(BaseCommand):
	help = 'Scrape the CM website for list of recent transactions'

	def add_arguments(self, parser):
		parser.add_argument('-q', '--quiet', action='store_true')

	def handle(self, *args, **options):
		if not settings.CM_USER_ACCOUNT:
			raise CommandError("Must specify CM user account in local_settings.py!")

		verbose = not options['quiet']

		curl = CurlWrapper()

		if verbose: self.stdout.write("Logging in...")
		curl.expect_redirect('https://www.creditmutuel.fr/en/authentification.html',
							 'https://www.creditmutuel.fr/en/banque/pageaccueil.html', {
								 '_cm_user': settings.CM_USER_ACCOUNT,
								 '_cm_pwd': settings.CM_USER_PASSWORD,
								 'flag': 'password',
							 })

		# Follow a redirect chain to collect more cookies
		curl.expect_redirect('https://www.creditmutuel.fr/en/banque/pageaccueil.html',
							 'https://www.creditmutuel.fr/en/banque/paci_engine/engine.aspx')
		got_redir = curl.expect_redirect('https://www.creditmutuel.fr/en/banque/paci_engine/engine.aspx',
										 ['https://www.creditmutuel.fr/en/banque/homepage_dispatcher.cgi',
										 'https://www.creditmutuel.fr/en/banque/paci_engine/static_content_manager.aspx'])
		if got_redir == 'https://www.creditmutuel.fr/en/banque/paci_engine/static_content_manager.aspx':
			# Got the "please fill out your personal data" form. So let's bypass it
			curl.expect_redirect('https://www.creditmutuel.fr/en/banque/paci_engine/static_content_manager.aspx?_productfilter=PACI&_pid=ContentManager&_fid=DoStopPaciAndRemind',
								 'https://www.creditmutuel.fr/en/banque/homepage_dispatcher.cgi')

		# Download the form
		if verbose: self.stdout.write("Downloading form...")
		(c,s) = curl.get('https://www.creditmutuel.fr/cmidf/en/banque/compte/telechargement.cgi')
		if c.getinfo(pycurl.RESPONSE_CODE) != 200:
			raise CommandError("Supposed to receive 200, got %s" % c.getinfo(c.RESPONSE_CODE))

		if verbose: self.stdout.write("Parsing form...")
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

		if verbose: self.stdout.write("Fetch report since {0}".format(fromdate))
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
			raise CommandException("Supposed to receive 200, got %s" % c.getinfo(c.RESPONSE_CODE))

		reader = csv.reader(s.getvalue().splitlines(), delimiter=';')

		# Write everything to the database
		with transaction.atomic():
			for row in reader:
				if row[0] == 'Operation date' or row[0] == 'Date':
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
					sys.stderr.write("Exception '{0}' when parsing row {1}".format(e, row))

		# Now send things off if there is anything to send
		with transaction.atomic():
			if CMutuelTransaction.objects.filter(sent=False).exclude(
					Q(description__startswith='VIR STG ADYEN ') |
					Q(description__startswith='VIR ADYEN BV ')
			).exists():
				sio = cStringIO.StringIO()
				sio.write("One or more new transactions have been recorded in the Credit Mutuel account:\n\n")
				sio.write("%-10s  %15s  %s\n" % ('Date', 'Amount', 'Description'))
				sio.write("-" * 50)
				sio.write("\n")
				for cmt in CMutuelTransaction.objects.filter(sent=False).order_by('opdate'):
					# Maybe this shouldn't be hardcoded, but for now it is.
					# Exclude Adyen transactions, since they are already reported separately.
					# Still flag them as sent though, so they don't queue up forever.
					if not (cmt.description.startswith('VIR STG ADYEN ') or cmt.description.startswith('VIR ADYEN BV ')):
						sio.write("%10s  %15s  %s\n" % (cmt.opdate, cmt.amount, cmt.description))

					cmt.sent = True
					cmt.save()
				send_simple_mail(settings.INVOICE_SENDER_EMAIL,
								 settings.INVOICE_SENDER_EMAIL,
								 'New Credit Mutuel transactions',
								 sio.getvalue())
