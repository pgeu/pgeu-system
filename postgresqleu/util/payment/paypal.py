from django.conf import settings
from urllib import urlencode

class Paypal(object):
	description="""
Using this payment method, you can pay via Paypal. You can use this both
to pay from your Paypal balance if you have a paypal account, or you can
use it to pay with any creditcard supported by Paypal (Visa, Mastercard, Amex).
You do not need a Paypal account if you choose to pay with creditcard.
"""

	PAYPAL_COMMON={
		'business':settings.PAYPAL_EMAIL,
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
			# We hardcode the return URL instead of sending it to the invoice,
			# so that we have one endpoint to deal with all the payment
			# data service packages.
			# If there is no return URL at all, we assume this payment doesn't
			# need any kind of quick feedback.
			param['return'] = 'https://www.postgresql.eu/p/paypal_return/'
			# However, if the user cancels, we send them back to the specified
			# return URL.
			param['cancel_return'] = returnurl
		return "%s?%s" % (
			settings.PAYPAL_BASEURL,
			urlencode(param))
