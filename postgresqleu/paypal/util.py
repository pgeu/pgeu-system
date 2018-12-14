from django.conf import settings

import urllib2
from urllib import urlencode
from urlparse import parse_qs
from decimal import Decimal
import itertools

class PaypalAPI(object):
    def __init__(self):
        self.accessparam = {
            'USER': settings.PAYPAL_API_USER,
            'PWD': settings.PAYPAL_API_PASSWORD,
            'SIGNATURE': settings.PAYPAL_API_SIGNATURE,
            'VERSION': 95,
        }
        if settings.PAYPAL_SANDBOX:
            self.API_ENDPOINT = 'https://api-3t.sandbox.paypal.com/nvp'
        else:
            self.API_ENDPOINT = 'https://api-3t.paypal.com/nvp'


    def _api_call(self, command, params):
        params.update(self.accessparam)
        params['METHOD'] = command
        resp = urllib2.urlopen(self.API_ENDPOINT, urlencode(params)).read()
        q = parse_qs(resp)
        if q['ACK'][0] != 'Success':
            raise Exception("API error from paypal: {0}/{1}".format(q['L_SHORTMESSAGE0'][0], q['L_LONGMESSAGE0'][0]))
        return q

    def _dateformat(self, d):
        return d.strftime("%Y-%m-%dT%H:%M:%S")

    def get_transaction_list(self, firstdate):
        r = self._api_call('TransactionSearch', {
            'STARTDATE': self._dateformat(firstdate),
            'STATUS': 'Success',
            })
        for i in itertools.count(0):
            if not r.has_key('L_TRANSACTIONID{0}'.format(i)):
                if i == 0:
                    # Special case as it seems inconsistent if it starts on 0 or on 1.
                    # So if there is no 0, just retry the loop at 1, and if there is still
                    # nothing, give up then.
                    continue
                break

            yield dict([(k,r.get('L_{0}{1}'.format(k, i),[''])[0])
                        for k in
                        ('TRANSACTIONID', 'TIMESTAMP', 'EMAIL', 'TYPE', 'AMT', 'FEEAMT', 'NAME')])


    def get_transaction_details(self, transactionid):
        return self._api_call('GetTransactionDetails', {
            'TRANSACTIONID': transactionid,
        })

    def get_primary_balance(self):
        r = self._api_call('GetBalance', {})
        if r['L_CURRENCYCODE0'][0] != settings.CURRENCY_ISO:
            raise Exception("Paypal primary currency reported as {0} instead of {1}!".format(
                r['L_CURRENCYCODE0'][0], settings.CURRENCY_ISO))
        return Decimal(r['L_AMT0'][0])

    def refund_transaction(self, paypaltransid, amount, isfull, refundnote):
        r = self._api_call('RefundTransaction', {
            'TRANSACTIONID': paypaltransid,
            'REFUNDTYPE': isfull and 'Full' or 'Partial',
            'AMT': '{0:.2f}'.format(amount),
            'CURRENCYCODE': settings.CURRENCY_ISO,
            'NOTE': refundnote,
        })

        # We ignore the status here as we will parse it from the
        # actual statement later.
        if r['ACK'][0] == 'Success':
            return r['REFUNDTRANSACTIONID'][0]

        raise Exception(r)
