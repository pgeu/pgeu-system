from django.conf import settings
from urllib import urlencode

class Paypal(object):
	description="""
Using this payment method, you can pay via Paypal. You can use this both
to pay from your Paypal balance if you have a paypal account, or you can
use it to pay with any creditcard supported by Paypal (Visa, Mastercard, Amex).
You do not need a Paypal account if you choose to pay with creditcard.
"""

	PAYPAL_BASEURL="https://www.paypal.com/cgi-bin/webscr?cmd"
	PAYPAL_SANBOXURL="https://www.sandbox.paypal.com/cgi-bin/webscr?cmd"
	PAYPAL_COMMON={
		'business':'paypal@postgresql.eu',
		'lc':'GB',
		'currency_code':'EUR',
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
			})
		if returnurl:
			param['return'] = returnurl
			param['cancel_return'] = returnurl
			param['rm'] = '1' # return method = GET without parameters
		return "%s%s" % (
			settings.PAYPAL_SANDBOX and self.PAYPAL_SANBOXURL or self.PAYPAL_BASEURL,
			urlencode(param))
