from django.conf import settings
from django.utils import timezone

import datetime
from decimal import Decimal
import requests
from requests.auth import HTTPBasicAuth

from .models import StripeCheckout, StripeRefund


class StripeException(Exception):
    pass


class StripeApi(object):
    APIBASE = "https://api.stripe.com/v1/"

    def __init__(self, pm):
        self.published_key = pm.config('published_key')
        self.secret_key = pm.config('secret_key')

    def _api_encode(self, params):
        for key, value in params.items():
            if isinstance(value, list) or isinstance(value, tuple):
                for i, subval in enumerate(value):
                    if isinstance(subval, dict):
                        subdict = self._encode_nested_dict("%s[%d]" % (key, i), subval)
                        yield from self._api_encode(subdict)
                    else:
                        yield ("%s[%d]" % (key, i), subval)
            elif isinstance(value, dict):
                subdict = self._encode_nested_dict(key, value)
                yield from self._api_encode(subdict)
            elif isinstance(value, datetime.datetime):
                yield (key, self._encode_datetime(value))
            else:
                yield (key, value)

    def _encode_nested_dict(self, key, data, fmt="%s[%s]"):
        d = {}
        for subkey, subvalue in data.items():
            d[fmt % (key, subkey)] = subvalue
        return d

    def secret(self, suburl, params=None, raise_for_status=True):
        if params:
            r = requests.post(self.APIBASE + suburl,
                              list(self._api_encode(params)),
                              auth=HTTPBasicAuth(self.secret_key, ''),
            )
        else:
            r = requests.get(self.APIBASE + suburl,
                             auth=HTTPBasicAuth(self.secret_key, ''),
            )
        if raise_for_status:
            r.raise_for_status()
        return r

    def get_balance(self):
        r = self.secret('balance').json()
        balance = Decimal(0)

        for a in r['available']:
            if a['currency'].lower() == settings.CURRENCY_ISO.lower():
                balance += Decimal(a['amount']) / 100
                break
        else:
            raise StripeException("No available balance entry found for currency {}".format(settings.CURRENCY_ISO))

        for p in r['pending']:
            if p['currency'].lower() == settings.CURRENCY_ISO.lower():
                balance += Decimal(p['amount']) / 100
                break
        else:
            raise StripeException("No pending balance entry found for currency {}".format(settings.CURRENCY_ISO))

        return balance

    def update_checkout_status(self, co):
        # Update the status of a payment. If it switched from unpaid to paid,
        # return True, otherwise False.
        if co.completedat:
            # Already completed!
            return False

        # We have to check the payment intent to get all the data that we
        # need, so we don't bother checking the co itself.

        r = self.secret('payment_intents/{}'.format(co.paymentintent)).json()
        if r['status'] == 'succeeded':
            # Before we flag it as done, we need to calculate the fees. Those we
            # can only find by loking at the charges, and from there finding the
            # corresponding balance transaction.
            if len(r['charges']['data']) != 1:
                raise StripeException("More than one charge found, not supported!")
            c = r['charges']['data'][0]
            if not c['paid']:
                return False
            if c['currency'].lower() != settings.CURRENCY_ISO.lower():
                raise StripeException("Found payment charge in currency {0}, expected {1}".format(c['currency'], settings.CURRENCY_ISO))

            txid = c['balance_transaction']
            t = self.secret('balance/history/{}'.format(txid)).json()
            if t['currency'].lower() != settings.CURRENCY_ISO.lower():
                raise StripeException("Found balance transaction in currency {0}, expected {1}".format(t['currency'], settings.CURRENCY_ISO))
            if t['exchange_rate']:
                raise StripeException("Found balance transaction with exchange rate set!")

            co.fee = Decimal(t['fee']) / 100
            co.completedat = timezone.now()
            co.save()

            return True
        # Still nothing
        return False

    def refund_transaction(self, co, amount, refundid):
        # To refund we need to find the charge id.
        r = self.secret('payment_intents/{}'.format(co.paymentintent)).json()
        if len(r['charges']['data']) != 1:
            raise StripeException("Number of charges is {}, not 1, don't know how to refund".format(len(r['charges']['data'])))
        chargeid = r['charges']['data'][0]['id']

        r = self.secret('refunds', {
            'charge': chargeid,
            'amount': int(amount * 100),
            'metadata': {
                'refundid': refundid,
            },
        }).json()

        refund = StripeRefund(paymentmethod=co.paymentmethod,
                              chargeid=chargeid,
                              invoicerefundid_id=refundid,
                              amount=amount,
                              refundid=r['id'])
        refund.save()

        return r['id']
