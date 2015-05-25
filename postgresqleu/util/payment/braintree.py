from postgresqleu.invoices.models import Invoice

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
