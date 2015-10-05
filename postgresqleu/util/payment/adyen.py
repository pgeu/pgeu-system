from django.conf import settings

from urllib import urlencode
from datetime import datetime, timedelta
import hmac
import hashlib
import base64
import gzip
import StringIO
import binascii
from collections import OrderedDict

from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.util import diff_workdays

def _escapeVal(val):
	return val.replace('\\','\\\\').replace(':','\\:')

def calculate_signature(param):
	param = OrderedDict(sorted(param.items(), key=lambda t: t[0]))
	if param.has_key('merchantSig'):
		del param['merchantSig']
	str = ':'.join(map(_escapeVal, param.keys() + param.values()))
	hm = hmac.new(binascii.a2b_hex(settings.ADYEN_SIGNKEY),
				  str,
				  hashlib.sha256)
	return base64.b64encode(hm.digest())

def _gzip_string(str):
	# Compress a string using gzip including header data
	s = StringIO.StringIO()
	g = gzip.GzipFile(fileobj=s, mode='w')
	g.write(str)
	g.close()
	return s.getvalue()

class _AdyenBase(object):
	ADYEN_COMMON={
		'currencyCode': settings.CURRENCY_ABBREV,
		'skinCode': settings.ADYEN_SKINCODE,
		'merchantAccount': settings.ADYEN_MERCHANTACCOUNT,
		'shopperLocale': 'en_GB',
		}

	def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl, allowedMethods, additionalparam):
		param = self.ADYEN_COMMON
		orderdata = "<p>%s</p>" % invoicestr
		param.update({
			'merchantReference': '%s%s' % (settings.ADYEN_MERCHANTREF_PREFIX, invoiceid),
			'paymentAmount': '%s' % (invoiceamount*100,),
			'orderData': base64.encodestring(_gzip_string(orderdata.encode('utf-8'))).strip().replace("\n",''),
			'merchantReturnData': '%s%s' % (settings.ADYEN_MERCHANTREF_PREFIX, invoiceid),
			'sessionValidity': (datetime.utcnow() + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ'),
			'allowedMethods': allowedMethods,
			})
		param.update(additionalparam)

		param['merchantSig'] = calculate_signature(param)

		# use pay.shtml for one-page, or select.shtml for multipage
		return "%shpp/select.shtml?%s" % (
			settings.ADYEN_BASEURL,
			urlencode(param),
			)

class AdyenCreditcard(_AdyenBase):
	description="""
Using this payment method, you can pay using your creditcard, including
Mastercard, VISA and American Express.
"""

	def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
		return super(AdyenCreditcard, self).build_payment_url(invoicestr, invoiceamount, invoiceid, returnurl, 'card', {})

class AdyenBanktransfer(_AdyenBase):
	description="""
Using this payment method, you can pay using a direct IBAN bank transfer.
"""

	def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
		i = Invoice.objects.get(pk=invoiceid)
		if i.recipient_secret:
			return "/invoices/adyen_bank/{0}/{1}/".format(invoiceid, i.recipient_secret)
		else:
			return "/invoices/adyen_bank/{0}/".format(invoiceid)

	def build_adyen_payment_url(self, invoicestr, invoiceamount, invoiceid):
		return super(AdyenBanktransfer, self).build_payment_url(invoicestr, invoiceamount, invoiceid, None, 'bankTransfer_IBAN', {
			'countryCode': 'FR',
			'skipSelection': 'true',
		})

	# Override availability for direct bank transfers. We hide it if the invoice will be
	# automatically canceled in less than 4 working days.
	def available(self, invoice):
		if invoice.canceltime:
			if diff_workdays(datetime.now(), invoice.canceltime) < 5:
				return False
		return True

	def unavailable_reason(self, invoice):
		if invoice.canceltime:
			if diff_workdays(datetime.now(), invoice.canceltime) < 5:
				return "Since this invoice will be automatically canceled in less than 5 working days, it requires the use of a faster payment method."
