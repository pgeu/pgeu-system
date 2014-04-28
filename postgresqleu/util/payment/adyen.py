from django.conf import settings

from urllib import urlencode
from datetime import datetime, timedelta
import hmac
import hashlib
import base64
import gzip
import StringIO

def calculate_signature(param, fields):
	str = "".join([param.has_key(f) and param[f] or '' for f in fields])
	hm = hmac.new(settings.ADYEN_SIGNKEY,
				  str,
				  hashlib.sha1)
	return base64.encodestring(hm.digest()).strip()

def _gzip_string(str):
	# Compress a string using gzip including header data
	s = StringIO.StringIO()
	g = gzip.GzipFile(fileobj=s, mode='w')
	g.write(str)
	g.close()
	return s.getvalue()

class AdyenCreditcard(object):
	description="""
Using this payment method, you can pay using your creditcard, including
Mastercard, VISA and American Express.
"""

	ADYEN_COMMON={
		'currencyCode': settings.CURRENCY_ABBREV,
		'skinCode': settings.ADYEN_SKINCODE,
		'merchantAccount': settings.ADYEN_MERCHANTACCOUNT,
		'shopperLocale': 'en_GB',
		}

	def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
		param = self.ADYEN_COMMON
		orderdata = "<p>%s</p>" % invoicestr
		param.update({
			'merchantReference': 'PGEU%s' % invoiceid,
			'paymentAmount': '%s' % (invoiceamount*100,),
			'orderData': base64.encodestring(_gzip_string(orderdata.encode('utf-8'))).strip().replace("\n",''),
			'merchantReturnData': 'PGEU%s' % invoiceid,
			'sessionValidity': (datetime.utcnow() + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ'),
			#shopperEmail - needs to be in the api
			#shopperId - needs to be in the api
			#allowedmethods/blockedmethods
			})
		param['merchantSig'] = calculate_signature(param, ('paymentAmount', 'currencyCode', 'merchantReference', 'skinCode', 'merchantAccount', 'sessionValidity', 'merchantReturnData', ))

		# use pay.shtml for one-page, or select.shtml for multipage
		return "%shpp/select.shtml?%s" % (
			settings.ADYEN_BASEURL,
			urlencode(param),
			)
