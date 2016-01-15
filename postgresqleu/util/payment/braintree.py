import re

from postgresqleu.invoices.models import Invoice
from postgresqleu.braintreepayment.models import BraintreeTransaction

class Braintree(object):
	description="""
Using this payment method, you can pay using your creditcard, including
Mastercard, VISA and American Express.
"""

	def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
		i = Invoice.objects.get(pk=invoiceid)
		if i.recipient_secret:
			return "/invoices/braintree/{0}/{1}/".format(invoiceid, i.recipient_secret)
		else:
			return "/invoices/braintree/{0}/".format(invoiceid)

	_re_braintree = re.compile('^Braintree id ([a-z0-9]+)$')
	def payment_fees(self, invoice):
		m = self._re_braintree.match(invoice.paymentdetails)
		if m:
			try:
				trans = BraintreeTransaction.objects.get(transid=m.groups(1)[0])
				if trans.disbursedamount:
					return "{0}{1}".format(settings.CURRENCY_SYMBOL, trans.amount-trans.disbursedamount)
				else:
					return "not disbursed yet"
			except BraintreeTransaction.DoesNotExist:
				return "not found"
		else:
			return "unknown format"
