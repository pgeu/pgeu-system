from django.conf import settings

import requests
from datetime import datetime, timedelta
from decimal import Decimal
import re
import uuid

from .models import TransferwiseRefund


class TransferwiseApi(object):
    def __init__(self, pm):
        self.pm = pm
        self.session = requests.session()
        self.session.headers.update({
            'Authorization': 'Bearer {}'.format(self.pm.config('apikey')),
        })

        self.profile = self.account = None

    def format_date(self, dt):
        return dt.strftime('%Y-%m-%dT00:00:00.000Z')

    def parse_datetime(self, s):
        return datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%fZ')

    def get(self, suburl, params=None):
        r = self.session.get(
            'https://api.transferwise.com/v1/{}'.format(suburl),
            params=params,
        )
        if r.status_code != 200:
            r.raise_for_status()
        return r.json()

    def post(self, suburl, params):
        r = self.session.post(
            'https://api.transferwise.com/v1/{}'.format(suburl),
            json=params,
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
            try:
                self.account = next((a for a in self.get('borderless-accounts', {'profileId': self.get_profile()}) if a['balances'][0]['currency'] == settings.CURRENCY_ABBREV))
            except Exception as e:
                raise Exception("Failed to get account: {}".format(e))
        return self.account

    def get_balance(self):
        for b in self.get_account()['balances']:
            if b['currency'] == settings.CURRENCY_ABBREV:
                return Decimal(b['amount']['value']).quantize(Decimal('0.01'))
        return None

    def get_transactions(self, startdate=None, enddate=None):
        if not enddate:
            enddate = (datetime.today() + timedelta(days=1)).date()

        if not startdate:
            startdate = enddate - timedelta(days=60)

        return self.get(
            'borderless-accounts/{0}/statement.json'.format(self.get_account()['id']),
            {
                'currency': settings.CURRENCY_ABBREV,
                'intervalStart': self.format_date(startdate),
                'intervalEnd': self.format_date(enddate),
            },
        )['transactions']

    def validate_iban(self, iban):
        return self.get('validators/iban?iban={}'.format(iban))['validation'] == 'success'

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
        acc = self.post(
            'accounts',
            {
                'profile': self.get_profile(),
                'currency': settings.CURRENCY_ABBREV,
                'accountHolderName': re.sub(r'\d+', '', counterpart_name),
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
            'transfers/{0}/payments'.format(transferid),
            {
                'type': 'BALANCE',
            },
        )

        return (accid, quoteid, transferid)
