from django.conf import settings

import urllib2
from urllib import urlencode
from urlparse import parse_qs
import itertools

class PaypalAPI(object):
	def __init__(self):
		self.accessparam = {
			'USER': settings.PAYPAL_API_USER,
			'PWD': settings.PAYPAL_API_PASSWORD,
			'SIGNATURE': settings.PAYPAL_API_SIGNATURE,
			'VERSION': 95,
		}
		if settings.PAYPAL_SANDBOX:
			self.API_ENDPOINT = 'https://api-3t.sandbox.paypal.com/nvp'
		else:
			self.API_ENDPOINT = 'https://api-3t.paypal.com/nvp'


	def _api_call(self, command, params):
		params.update(self.accessparam)
		params['METHOD'] = command
		resp = urllib2.urlopen(self.API_ENDPOINT, urlencode(params)).read()
		q = parse_qs(resp)
		if q['ACK'][0] != 'Success':
			raise Exception("API error from paypal: {0}/{1}".format(q['L_SHORTMESSAGE0'][0], q['L_LONGMESSAGE0'][0]))
		return q

	def _dateformat(self, d):
		return d.strftime("%Y-%m-%dT%H:%M:%S")

	def get_transaction_list(self, firstdate):
		r = self._api_call('TransactionSearch', {
			'STARTDATE': self._dateformat(firstdate),
			'STATUS': 'Success',
			})
		for i in itertools.count(1):
			if not r.has_key('L_TRANSACTIONID{0}'.format(i)):
				break

			yield dict([(k,r.get('L_{0}{1}'.format(k, i),[''])[0])
						for k in
						('TRANSACTIONID', 'TIMESTAMP', 'EMAIL', 'TYPE', 'AMT', 'FEEAMT', 'NAME')])


	def get_transaction_details(self, transactionid):
		return self._api_call('GetTransactionDetails', {
			'TRANSACTIONID': transactionid,
		})
