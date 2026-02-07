from django.conf import settings
from django.utils import timezone

import requests
from requests.auth import HTTPBasicAuth
from decimal import Decimal
from datetime import datetime, timedelta


class PaypalAPI(object):
    BASE_HEADERS = {
        'Accept': 'application/json',
        'Accept-Language': 'en_US',
    }

    def __init__(self, pm):
        self.token = None
        self.pm = pm
        if pm.config('sandbox'):
            self.REST_ENDPOINT = 'https://api.sandbox.paypal.com/'
        else:
            self.REST_ENDPOINT = 'https://api.paypal.com/'

    def ensure_access_token(self):
        if not self.token:
            r = requests.post(
                '{0}v1/oauth2/token'.format(self.REST_ENDPOINT),
                headers=self.BASE_HEADERS,
                data={
                    'grant_type': 'client_credentials',
                },
                auth=HTTPBasicAuth(self.pm.config('clientid'), self.pm.config('clientsecret')),
            )
            if r.status_code != 200:
                r.raise_for_status()
            j = r.json()
            self.token = j['access_token']
            self.tokenscope = j['scope']

    def _authorized_headers(self):
        self.ensure_access_token()
        h = self.BASE_HEADERS.copy()
        h['Authorization'] = 'Bearer ' + self.token
        return h

    def _rest_api_call(self, suburl, params):
        return requests.get('{0}{1}'.format(self.REST_ENDPOINT, suburl),
                            params=params,
                            headers=self._authorized_headers(),
        )

    def _rest_api_post(self, suburl, json):
        self.ensure_access_token()
        h = self.BASE_HEADERS.copy()
        h['Authorization'] = 'Bearer ' + self.token
        return requests.post('{0}{1}'.format(self.REST_ENDPOINT, suburl),
                             json=json,
                             headers=self._authorized_headers(),
        )

    def _dateformat(self, d):
        return d.strftime("%Y-%m-%dT%H:%M:%S+0000")

    def get_transaction_list(self, startdate):
        r = self._rest_api_call('v1/reporting/transactions/', {
            'start_date': self._dateformat(startdate),
            'end_date': self._dateformat(startdate + timedelta(days=30)),
            'fields': 'transaction_info,payer_info,shipping_info,cart_info',
            'page_size': 500,
        })
        if r.status_code != 200:
            raise Exception("Failed to get transactions: %s" % r.json()['message'])

        for t in r.json().get('transaction_details', []):
            if t['transaction_info']['transaction_status'] != 'S':
                continue

            if t['transaction_info']['transaction_amount']['currency_code'] != settings.CURRENCY_ISO:
                raise Exception("Transaction {0} is wrong currency: {1}".format(
                    t['transaction_info']['transaction_id'],
                    t['transaction_info']['transaction_amount']['currency_code'],
                ))

            code = t['transaction_info']['transaction_event_code']
            r = {
                'TRANSACTIONID': t['transaction_info']['transaction_id'],
                'TIMESTAMP': t['transaction_info']['transaction_updated_date'],
                'AMT': t['transaction_info']['transaction_amount']['value'],
                'EMAIL': None,
                'NAME': None,
                'SUBJECT': None,
            }

            if code in ('T1105', ):
                # Some things are better left ignored
                continue

            if code in ('T2101', 'T2102'):
                # General hold and release of general hold. Ignore those.
                continue

            if code in ('T0400', 'T0401', 'T0403'):
                # General withdrawal, doesn't have normal details
                r['EMAIL'] = self.pm.config('email')
                r['NAME'] = self.pm.config('email')
                r['SUBJECT'] = 'Transfer from Paypal to bank'
                yield r
                continue

            if code == 'T0300':
                # General funding of paypal account, such as a direct debit
                r['EMAIL'] = self.pm.config('email')
                r['NAME'] = self.pm.config('email')
                r['SUBJECT'] = 'Funding of Paypal account'
                yield r
                continue

            if code == 'T0303':
                # Bank deposit, doesn't have normal details
                r['EMAIL'] = self.pm.config('email')
                r['NAME'] = self.pm.config('email')
                r['SUBJECT'] = 'Bank deposit to paypal'
                yield r
                continue

            if code == 'T1201':
                # Chargeback, also doesn't have normal details
                r['EMAIL'] = self.pm.config('email')
                r['NAME'] = self.pm.config('email')
                r['SUBJECT'] = 'Paypal chargeback'
                yield r
                continue

            if code in ('T1106', 'T1108', 'T0106'):
                # "Payment reversal, initiated by PayPal", *sometimes* has email and
                # sometimes not. Undocumented when they differ.
                # T0106 is chargeback fee, also from no real sender
                r['EMAIL'] = t['payer_info'].get('email_address', self.pm.config('email'))

            if not r['EMAIL']:
                # Seems with some type of transfers things can show up with non-existent
                # email addresses which shouldn't happen. We'll just have to fall back to our
                # own which we know is wrong, but we also know it exists-
                r['EMAIL'] = t['payer_info'].get('email_address', self.pm.config('email'))

            # Figure out the name, since it can be in completely different places
            # depending on the transaction (even for the same type of transactions)
            if 'name' in t['shipping_info']:
                r['NAME'] = t['shipping_info']['name']
            elif 'payer_name' in t['payer_info']:
                if 'given_name' in t['payer_info']['payer_name']:
                    r['NAME'] = "{0} {1}".format(t['payer_info']['payer_name']['given_name'], t['payer_info']['payer_name']['surname'])
                elif 'alternate_full_name' in t['payer_info']['payer_name']:
                    r['NAME'] = t['payer_info']['payer_name']['alternate_full_name']

            # If we haven't found a name on the transaction *anywhere*, set the name field to
            # the email address.
            if not r['NAME']:
                r['NAME'] = r['EMAIL']

            if 'fee_amount' in t['transaction_info']:
                r['FEEAMT'] = t['transaction_info']['fee_amount']['value']

            if code in ('T0000', 'T0001', 'T0003', 'T0006', 'T0007', 'T0011', 'T0013', 'T0700'):
                if 'item_details' in t['cart_info']:
                    r['SUBJECT'] = t['cart_info']['item_details'][0]['item_name']
                elif 'transaction_note' in t['transaction_info']:
                    r['SUBJECT'] = t['transaction_info']['transaction_note']
                else:
                    r['SUBJECT'] = 'Paypal payment with empty note'
            elif code == 'T0002':
                r['SUBJECT'] = 'Recurring paypal payment without note'
            elif code == 'T1107':
                if t['transaction_info'].get('transaction_subject', ''):
                    r['SUBJECT'] = 'Refund of Paypal payment: %s' % t['transaction_info']['transaction_subject']
                else:
                    r['SUBJECT'] = 'Refund of unknown transaction'
            elif code == 'T1106':
                # Payment reversal initiated by paypal
                r['SUBJECT'] = 'Reversal of {0}'.format(t['transaction_info']['paypal_reference_id'])
            elif code == 'T1108':
                r['SUBJECT'] = 'Reversal of fee for {0}'.format(t['transaction_info']['paypal_reference_id'])
            elif code == 'T0106':
                r['SUBJECT'] = 'Paypal chargeback fee for {0}'.format(t['transaction_info']['paypal_reference_id'])
            else:
                raise Exception("Unknown paypal transaction event code %s" % code)

            yield r

    def get_primary_balance(self):
        r = self._rest_api_call('v1/reporting/balances', {
            'currency_code': settings.CURRENCY_ISO,
        })
        if r.status_code != 200:
            raise Exception("Failed to get paypal balance: %s" % r.json()['message'])
        j = r.json()

        for b in j['balances']:
            if b['primary']:
                if b['currency'] != settings.CURRENCY_ISO:
                    raise Exception("Mismatched currency on primary account: %s" % j['balances'])
                if b['total_balance']['currency_code'] != settings.CURRENCY_ISO:
                    raise Exception("Mismatched currency on total balance: %s" % b)
                return Decimal(b['total_balance']['value'])

        raise Exception("No primary balance found in %s" % j['balances'])

    def refund_transaction(self, paypaltransid, amount, isfull, refundnote):
        r = self._rest_api_post(
            'v1/payments/sale/{0}/refund'.format(paypaltransid),
            {
                'amount': {
                    'total': '{0:.2f}'.format(amount),
                    'currency': settings.CURRENCY_ISO,
                },
                'description': refundnote,
            }
        )
        if r.status_code != 201:
            raise Exception("Failed to issue refund: %s" % r.json()['message'])
        return r.json()['id']
