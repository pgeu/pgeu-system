from django.core.serializers.json import DjangoJSONEncoder
from django.conf import settings

import requests
from datetime import datetime, timedelta
from decimal import Decimal
import json
import re
import sys
import uuid
from base64 import b64encode

from postgresqleu.util.time import today_global
from postgresqleu.util.crypto import rsa_sign_string_sha256
from .models import TransferwiseRefund


class TransferwiseApi(object):
    def __init__(self, pm):
        self.pm = pm
        self.session = requests.session()
        self.session.headers.update({
            'Authorization': 'Bearer {}'.format(self.pm.config('apikey')),
        })
        self.privatekey = self.pm.config('private_key')

        self.profile = self.account = None

    def format_date(self, dt):
        return dt.strftime('%Y-%m-%dT00:00:00.000Z')

    def parse_datetime(self, s):
        return datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%fZ')

    def _sign_2fa_token(self, token):
        if not self.privatekey:
            raise Exception("Two factor authentication required but no private key configured")
        return b64encode(rsa_sign_string_sha256(self.privatekey, token))

    def _get(self, suburl, params=None, stream=False, version='v1'):
        fullurl = 'https://api.transferwise.com/{}/{}'.format(version, suburl)
        r = self.session.get(
            fullurl,
            params=params,
            stream=stream,
        )
        if r.status_code == 403 and 'X-2FA-Approval' in r.headers:
            # This was a request for 2FA authenticated access
            token = r.headers['X-2FA-Approval']
            r = self.session.get(
                fullurl,
                params=params,
                stream=stream,
                headers={
                    'x-2fa-approval': token,
                    'x-signature': self._sign_2fa_token(token),
                },
            )
        if r.status_code != 200:
            # Print the content of the error as well, so this can be picked up in a log
            sys.stderr.write("API returned status {}. Body:\n{}".format(r.status_code, r.text[:2000]))
            r.raise_for_status()
        return r

    def get(self, suburl, params=None, version='v1'):
        return self._get(suburl, params, False, version).json()

    def get_binary(self, suburl, params=None, version='v1'):
        r = self._get(suburl, params, True, version)
        r.raw.decode_content = True
        return r.raw

    def post(self, suburl, params, version='v1'):
        j = json.dumps(params, cls=DjangoJSONEncoder)
        fullurl = 'https://api.transferwise.com/{}/{}'.format(version, suburl)
        r = self.session.post(
            fullurl,
            data=j,
            headers={
                'Content-Type': 'application/json',
            },
        )
        if r.status_code == 403 and 'X-2FA-Approval' in r.headers:
            # This was a request for 2FA authenticated access
            token = r.headers['X-2FA-Approval']
            r = self.session.post(
                fullurl,
                data=j,
                headers={
                    'Content-Type': 'application/json',
                    'x-2fa-approval': token,
                    'x-signature': self._sign_2fa_token(token),
                },
            )
        r.raise_for_status()
        return r.json()

    def get_profile(self):
        if not self.profile:
            try:
                self.profile = next((p['id'] for p in self.get('profiles') if p['type'] == 'business'))
            except Exception as e:
                raise Exception("Failed to get profile: {}".format(e))
            pass
        return self.profile

    def get_account(self):
        if not self.account:
            for a in self.get('borderless-accounts', {'profileId': self.get_profile()}):
                # Each account has multiple currencies, so we look for the first one that
                # has our currency somewhere.
                for b in a['balances']:
                    if b['currency'] == settings.CURRENCY_ABBREV:
                        self.account = a
                        break

                if self.account:
                    # If we found our currency on this account, use it
                    break

            if not self.account:
                raise Exception("Failed to identify account based on currency")
        return self.account

    def get_balance(self):
        for b in self.get_account()['balances']:
            if b['currency'] == settings.CURRENCY_ABBREV:
                return Decimal(b['amount']['value']).quantize(Decimal('0.01'))
        return None

    def get_transactions(self, startdate=None, enddate=None):
        if not enddate:
            enddate = today_global() + timedelta(days=1)

        if not startdate:
            startdate = enddate - timedelta(days=60)

        return self.get(
            'profiles/{}/borderless-accounts/{}/statement.json'.format(self.get_profile(), self.get_account()['id']),
            {
                'currency': settings.CURRENCY_ABBREV,
                'intervalStart': self.format_date(startdate),
                'intervalEnd': self.format_date(enddate),
            },
            version='v3',
        )['transactions']

    def validate_iban(self, iban):
        try:
            return self.get('validators/iban?iban={}'.format(iban))['validation'] == 'success'
        except requests.exceptions.HTTPError as e:
            # API returns http 400 on (some?) failed validations that are just not validating.
            # In those cases, just set it to not being valid.
            if e.response.status_code == 400:
                return False

            # Bubble any other exceptions
            raise

    def get_structured_amount(self, amount):
        if amount['currency'] != settings.CURRENCY_ABBREV:
            raise Exception("Invalid currency {} found, exepcted {}".format(amount['currency'], settings.CURRENCY_ABBREV))
        return Decimal(amount['value']).quantize(Decimal('0.01'))

    def refund_transaction(self, origtrans, refundid, refundamount, refundstr):
        if not origtrans.counterpart_valid_iban:
            raise Exception("Cannot refund transaction without valid counterpart IBAN!")

        # This is a many-step process, unfortunately complicated.
        twr = TransferwiseRefund(origtransaction=origtrans, uuid=uuid.uuid4(), refundid=refundid)

        (accid, quoteid, transferid) = self.make_transfer(origtrans.counterpart_name,
                                                          origtrans.counterpart_account,
                                                          refundamount,
                                                          refundstr,
                                                          twr.uuid,
        )
        twr.accid = accid
        twr.quoteid = quoteid
        twr.transferid = transferid
        twr.save()
        return twr.id

    def make_transfer(self, counterpart_name, counterpart_account, amount, reference, xuuid):
        # Create a recipient account
        name = re.sub(r'\d+', '', counterpart_name.replace(',', ' '))
        if ' ' not in name:
            # Transferwise requires at least a two part name. Since the recipient name
            # isn't actually important, just duplicate it...
            name = name + ' ' + name

        acc = self.post(
            'accounts',
            {
                'profile': self.get_profile(),
                'currency': settings.CURRENCY_ABBREV,
                'accountHolderName': name,
                'type': 'iban',
                'details': {
                    'IBAN': counterpart_account,
                },
            }
        )
        accid = acc['id']

        # Create a quote (even though we're not doing currency exchange)
        quote = self.post(
            'quotes',
            {
                'profile': self.get_profile(),
                'source': settings.CURRENCY_ABBREV,
                'target': settings.CURRENCY_ABBREV,
                'rateType': 'FIXED',
                'targetAmount': amount,
                'type': 'BALANCE_PAYOUT',
            },
        )
        quoteid = quote['id']

        # Create the actual transfer
        transfer = self.post(
            'transfers',
            {
                'targetAccount': accid,
                'quote': quoteid,
                'customerTransactionId': str(xuuid),
                'details': {
                    'reference': reference,
                },
            },
        )
        transferid = transfer['id']

        # Fund the transfer from our account
        fund = self.post(
            'profiles/{}/transfers/{}/payments'.format(self.get_profile(), transferid),
            {
                'type': 'BALANCE',
            },
            version='v3',
        )

        return (accid, quoteid, transferid)
