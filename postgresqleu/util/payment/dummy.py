from postgresqleu.invoices.models import Invoice


class DummyPayment(object):
    description = """
This is a payment method purely for debugging. If you see this in production,
please let the administrator know immediately!
"""

    def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
        i = Invoice.objects.get(pk=invoiceid)
        if i.recipient_secret:
            return "/invoices/dummy/{0}/{1}/".format(invoiceid, i.recipient_secret)
        else:
            return "/invoices/dummy/{0}/".format(invoiceid)
