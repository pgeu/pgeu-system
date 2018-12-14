from urllib import urlencode


class Banktransfer(object):
    description = """
Using this payment method, you can pay via a regular bank transfer
using IBAN. Note that this requires that you are able to make a
payment in Euros, and requires you to cover all transfer charges.
"""

    def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
        param = {
            'title': invoicestr.encode('utf-8'),
            'amount': invoiceamount,
            }
        if returnurl:
            param['ret'] = returnurl
        return "/invoices/banktransfer/?%s" % urlencode(param)
