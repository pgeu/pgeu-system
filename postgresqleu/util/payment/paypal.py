from django.conf import settings
from urllib import urlencode

import re

from postgresqleu.paypal.models import TransactionInfo
from postgresqleu.paypal.util import PaypalAPI

class Paypal(object):
	description="""
Pay using Paypal. You can use this both
to pay from your Paypal balance if you have a Paypal account, or you can
use it to pay with any credit card supported by Paypal (Visa, Mastercard, American Express).
In most countries, you do not need a Paypal account if you choose to pay
with credit card. However, we do recommend using the payment method called
"Credit card" instead of Paypal if you are paying with a credit card, as it has
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
			'amount': '%.2f' % invoiceamount,
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
	def _find_invoice_transaction(self, invoice):
		m = self._re_paypal.match(invoice.paymentdetails)
		if m:
			try:
				return (TransactionInfo.objects.get(paypaltransid=m.groups(1)[0]), None)
			except TransactionInfo.DoesNotExist:
				return (None, "not found")
		else:
			return (None, "unknown format")

	def payment_fees(self, invoice):
		(trans, reason) = self._find_invoice_transaction(invoice)
		if not trans:
			return reason

		return trans.fee

	def autorefund(self, invoice):
		(trans, reason) = self._find_invoice_transaction(invoice)
		if not trans:
			raise Exception(reason)

		api = PaypalAPI()
		invoice.refund.payment_reference = api.refund_transaction(
			trans.paypaltransid,
			invoice.refund.fullamount,
			invoice.refund.fullamount == invoice.total_amount,
			'{0} refund {1}'.format(settings.ORG_SHORTNAME, invoice.refund.id),
		)
		# At this point, we succeeded. Anything that failed will bubble
		# up as an exception.
		return True

	def used_method_details(self, invoice):
		# Bank transfers don't need any extra information
		return "PayPal"
