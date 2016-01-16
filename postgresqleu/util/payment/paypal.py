from django.conf import settings
from urllib import urlencode

import re

from postgresqleu.paypal.models import TransactionInfo

class Paypal(object):
	description="""
Using this payment method, you can pay via Paypal. You can use this both
to pay from your Paypal balance if you have a Paypal account, or you can
use it to pay with any creditcard supported by Paypal (Visa, Mastercard, American Express).
In most countries, you do not need a Paypal account if you choose to pay
with creditcard. However, we do recommend using the payment method called
"Credit card" instead of Paypal if you are paying with a creditcard, as it has
lower fees.
"""

	PAYPAL_COMMON={
		'business':settings.PAYPAL_EMAIL,
		'lc':'GB',
		'currency_code': settings.CURRENCY_ABBREV,
		'button_subtype':'services',
		'no_note':'1',
		'no_shipping':'1',
		'bn':'PP-BuyNowBF:btn_buynowCC_LG.gif-NonHosted',
		'charset':'utf-8',
		}

	def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
		param = self.PAYPAL_COMMON
		param.update({
			'cmd': '_xclick',
			'item_name': invoicestr.encode('utf-8'),
			'amount': '%s.00' % invoiceamount,
			'invoice': invoiceid,
			'return': '%s/p/paypal_return/' % settings.SITEBASE,
			})
		if returnurl:
			# If the user cancels, send back to specific URL, instead of
			# the invoice url.
			param['cancel_return'] = returnurl
		return "%s?%s" % (
			settings.PAYPAL_BASEURL,
			urlencode(param))

	_re_paypal = re.compile('^Paypal id ([A-Z0-9]+), ')
	def payment_fees(self, invoice):
		# Find the paypal transaction based on the invoice payment info.
		m = self._re_paypal.match(invoice.paymentdetails)
		if m:
			try:
				trans = TransactionInfo.objects.get(paypaltransid=m.groups(1)[0])
				return "{0}{1}".format(settings.CURRENCY_SYMBOL, trans.fee)
			except TransactionInfo.DoesNotExist:
				return "not found"
		else:
			return "unknown format"
