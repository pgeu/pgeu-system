import re

from postgresqleu.invoices.models import Invoice
from postgresqleu.braintreepayment.models import BraintreeTransaction

class Braintree(object):
    description="""
Using this payment method, you can pay using your credit card, including
Mastercard, VISA and American Express.
"""

    def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
        i = Invoice.objects.get(pk=invoiceid)
        if i.recipient_secret:
            return "/invoices/braintree/{0}/{1}/".format(invoiceid, i.recipient_secret)
        else:
            return "/invoices/braintree/{0}/".format(invoiceid)

    _re_braintree = re.compile('^Braintree id ([a-z0-9]+)$')
    def _find_invoice_transaction(self, invoice):
        m = self._re_braintree.match(invoice.paymentdetails)
        if m:
            try:
                return (BraintreeTransaction.objects.get(transid=m.groups(1)[0]), None)
            except BraintreeTransaction.DoesNotExzist:
                return (None, "not found")
        else:
            return (None, "unknown format")

    def payment_fees(self, invoice):
        (trans, reason) = self._find_invoice_transaction(invoice)
        if not trans:
            return reason
        if trans.disbursedamount:
            return trans.amount-trans.disbursedamount
        else:
            return "not disbursed yet"

    def used_method_details(self, invoice):
        (trans, reason) = self._find_invoice_transaction(invoice)
        if not trans:
            raise Exception(reason)
        return "Credit Card ({0})".format(trans.method)
