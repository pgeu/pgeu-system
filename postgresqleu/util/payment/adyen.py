from django.conf import settings

from urllib import urlencode
from datetime import datetime, timedelta
from decimal import Decimal
import hmac
import hashlib
import base64
import gzip
import StringIO
import binascii
from collections import OrderedDict

import re

from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.util import diff_workdays
from postgresqleu.adyen.models import TransactionStatus
from postgresqleu.adyen.util import AdyenAPI

def _escapeVal(val):
    return val.replace('\\', '\\\\').replace(':', '\\:')

def calculate_signature(param):
    param = OrderedDict(sorted(param.items(), key=lambda t: t[0]))
    if param.has_key('merchantSig'):
        del param['merchantSig']
    str = ':'.join(map(_escapeVal, param.keys() + param.values()))
    hm = hmac.new(binascii.a2b_hex(settings.ADYEN_SIGNKEY),
                  str,
                  hashlib.sha256)
    return base64.b64encode(hm.digest())

def _gzip_string(str):
    # Compress a string using gzip including header data
    s = StringIO.StringIO()
    g = gzip.GzipFile(fileobj=s, mode='w')
    g.write(str)
    g.close()
    return s.getvalue()

class _AdyenBase(object):
    ADYEN_COMMON = {
        'currencyCode': settings.CURRENCY_ABBREV,
        'skinCode': settings.ADYEN_SKINCODE,
        'merchantAccount': settings.ADYEN_MERCHANTACCOUNT,
        'shopperLocale': 'en_GB',
        }

    def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl, allowedMethods, additionalparam):
        param = self.ADYEN_COMMON
        orderdata = "<p>%s</p>" % invoicestr
        param.update({
            'merchantReference': '%s%s' % (settings.ADYEN_MERCHANTREF_PREFIX, invoiceid),
            'paymentAmount': '%s' % (int(invoiceamount * Decimal(100.0)),),
            'orderData': base64.encodestring(_gzip_string(orderdata.encode('utf-8'))).strip().replace("\n", ''),
            'merchantReturnData': '%s%s' % (settings.ADYEN_MERCHANTREF_PREFIX, invoiceid),
            'sessionValidity': (datetime.utcnow() + timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'allowedMethods': allowedMethods,
            })
        param.update(additionalparam)

        param['merchantSig'] = calculate_signature(param)

        # use pay.shtml for one-page, or select.shtml for multipage
        return "%shpp/select.shtml?%s" % (
            settings.ADYEN_BASEURL,
            urlencode(param),
            )

    _re_adyen = re.compile('^Adyen id ([A-Z0-9]+)$')
    def _find_invoice_transaction(self, invoice):
        m = self._re_adyen.match(invoice.paymentdetails)
        if m:
            try:
                return (TransactionStatus.objects.get(pspReference=m.groups(1)[0]), None)
            except TransactionStatus.DoesNotExist:
                return (None, "not found")
        else:
            return (None, "unknown format")

    def payment_fees(self, invoice):
        (trans, reason) = self._find_invoice_transaction(invoice)
        if not trans:
            return reason

        if trans.settledamount:
            return trans.amount - trans.settledamount
        else:
            return "not settled yet"

    def autorefund(self, invoice):
        (trans, reason) = self._find_invoice_transaction(invoice)
        if not trans:
            raise Exception(reason)

        api = AdyenAPI()
        invoice.refund.payment_reference = api.refund_transaction(
            invoice.refund.id,
            trans.pspReference,
            invoice.refund.fullamount,
        )
        # At this point, we succeeded. Anything that failed will bubble
        # up as an exception.
        return True

class AdyenCreditcard(_AdyenBase):
    description = """
Pay using your credit card, including Mastercard, VISA and American Express.
"""

    def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
        return super(AdyenCreditcard, self).build_payment_url(invoicestr, invoiceamount, invoiceid, returnurl, 'card', {})

    def used_method_details(self, invoice):
        # For credit card payments we try to figure out which type of
        # card it is as well.
        (trans, reason) = self._find_invoice_transaction(invoice)
        if not trans:
            raise Exception(reason)
        return "Credit Card ({0})".format(trans.method)

class AdyenBanktransfer(_AdyenBase):
    description = """
Pay using a direct IBAN bank transfer. Due to the unreliable and slow processing
of these payments, this method is <b>not recommended</b> unless it is the only
option possible. In particular, we strongly advice not using this method if
making a payment from outside the Euro-zone.
"""

    def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
        i = Invoice.objects.get(pk=invoiceid)
        if i.recipient_secret:
            return "/invoices/adyen_bank/{0}/{1}/".format(invoiceid, i.recipient_secret)
        else:
            return "/invoices/adyen_bank/{0}/".format(invoiceid)

    def build_adyen_payment_url(self, invoicestr, invoiceamount, invoiceid):
        return super(AdyenBanktransfer, self).build_payment_url(invoicestr, invoiceamount, invoiceid, None, 'bankTransfer_IBAN', {
            'countryCode': 'FR',
            'skipSelection': 'true',
        })

    # Override availability for direct bank transfers. We hide it if the invoice will be
    # automatically canceled in less than 4 working days.
    def available(self, invoice):
        if invoice.canceltime:
            if diff_workdays(datetime.now(), invoice.canceltime) < 5:
                return False
        return True

    def unavailable_reason(self, invoice):
        if invoice.canceltime:
            if diff_workdays(datetime.now(), invoice.canceltime) < 5:
                return "Since this invoice will be automatically canceled in less than 5 working days, it requires the use of a faster payment method."

    def used_method_details(self, invoice):
        # Bank transfers don't need any extra information
        return "IBAN bank transfers"
