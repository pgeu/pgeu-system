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
from postgresqleu.mailqueue.util import send_simple_mail

from .models import TransferwiseRefund


class TransferwiseApi(object):
    def __init__(self, pm):
        self.pm = pm
        self.session = requests.session()
        self.session.headers.update({
            'Authorization': 'Bearer {}'.format(self.pm.config('apikey')),
        })
        self.privatekey = self.pm.config('private_key')

        self.profile = self.balances = None

    def format_date(self, dt):
        return dt.strftime('%Y-%m-%dT00:00:00.000Z')

    def parse_datetime(self, s):
        try:
            return datetime.strptime(s, '%Y-%m-%dT%H:%M:%S.%fZ')
        except ValueError:
            # Why would tw consistently have just one way to write timestamps? That would be silly!
            return datetime.strptime(s, '%Y-%m-%d %H:%M:%S')

    def _get(self, suburl, params=None, stream=False, version='v1'):
        fullurl = 'https://api.transferwise.com/{}/{}'.format(version, suburl)
        r = self.session.get(
            fullurl,
            params=params,
            stream=stream,
        )
        if r.status_code != 200:
            # Print the content of the error as well, so this can be picked up in a log
            sys.stderr.write("API returned status {}. Body:\n{}\n".format(r.status_code, r.text[:2000]))
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

    def _get_balances(self):
        if not self.balances:
            self.balances = self.get('profiles/{}/balances'.format(self.get_profile()), params={'types': 'STANDARD'}, version='v4')
        return self.balances

    def get_account(self):
        for a in self._get_balances():
            if a['currency'] == settings.CURRENCY_ABBREV:
                return a['id']
        raise Exception("Failed to identify account based on currency")

    def get_account_details(self):
        for d in self.get('profiles/{}/account-details'.format(self.get_profile())):
            if d['id'] and d['status'] == 'ACTIVE' and d['currency']['code'] == settings.CURRENCY_ABBREV:
                for o in d['receiveOptions']:
                    if o['type'] == 'INTERNATIONAL':
                        return o['shareText']
        raise Exception("Could not find account in returned structure")

    def get_balance(self):
        for b in self._get_balances():
            if b['currency'] == settings.CURRENCY_ABBREV:
                return Decimal(b['amount']['value']).quantize(Decimal('0.01'))
        return None

    def get_transactions(self, startdate=None, enddate=None):
        if not enddate:
            enddate = today_global() + timedelta(days=1)

        if not startdate:
            startdate = enddate - timedelta(days=60)

        cursor = None
        while True:
            params = {'since': self.format_date(startdate), 'until': self.format_date(enddate), 'status': 'COMPLETED', 'size': 100}
            if cursor:
                params['nextCursor'] = cursor
            r = self.get('profiles/{}/activities'.format(self.get_profile()), params)
            if not r['activities']:
                # No more activities!
                return

            for activity in r['activities']:
                if activity['type'] == 'TRANSFER' or \
                   activity['type'] == 'DIRECT_DEBIT_TRANSACTION' or \
                   (activity['type'] == 'BALANCE_DEPOSIT' and activity['resource']['type'] == 'TRANSFER'):
                    try:
                        details = self.get('transfers/{}'.format(activity['resource']['id']))

                        if details['sourceCurrency'] != settings.CURRENCY_ABBREV:
                            continue

                        amount = Decimal(details['targetValue']).quantize(Decimal('0.01'))
                        created = details['created']
                        reference = details['reference']
                        fulldescription = details['details']['reference']
                    except requests.exceptions.HTTPError as e:
                        if e.response.status_code == 403:
                            # No permissions can mean (1) it's a wise-to-wise transaction, for which we are not allowed to
                            # see details, or (2) a direct debit transaction.
                            print("No permissions to access transaction {} from {}, adding placeholder without details".format(
                                activity['resource']['id'],
                                activity['updatedOn'],
                            ))

                            amount, currency = self.parse_transferwise_amount(activity['primaryAmount'])
                            if currency != settings.CURRENCY_ABBREV:
                                # This is transaction is in a different currency, so ignore it
                                continue
                            created = activity['createdOn']
                            reference = ''
                            fulldescription = 'Transaction with no permissions on details: {}'.format(self.strip_tw_tags(activity['title']))
                        else:
                            raise

                    # Yes, the transfer will actually have a positive amount even if it's a withdrawal.
                    # No, this is not indicated anywhere, since the "target account id" that would
                    # indicate it, points to the wrong account for incoming payments.
                    # Oh, and the status is *always* set to `outgoing_payment_sent`, even for incoming
                    # payments. I guess all payments are outgoing from *something*.
                    # Let's do a wild gamble and assume the description is always this...
                    if activity.get('description', '').startswith('Sent by '):
                        negatizer = -1
                    else:
                        negatizer = 1

                    # We also need to look at the amount in the activity, as it might be different
                    # if there are fees.
                    primaryAmount, primaryCurrency = self.parse_transferwise_amount(activity['primaryAmount'])
                    if activity.get('secondaryAmount', None):
                        secondaryAmount, secondaryCurrency = self.parse_transferwise_amount(activity['secondaryAmount'])
                    else:
                        secondaryAmount = 0
                        secondaryCurrency = primaryCurrency

                    if primaryCurrency != secondaryCurrency:
                        # This is (preasumably) an outgoing payment in a non-primary currency. In this case, the EUR numbers are in
                        # the secondaryCurrency fields.
                        amount = secondaryAmount
                    elif primaryCurrency != settings.CURRENCY_ABBREV:
                        print(activity)
                        raise Exception("Primary currency is not our primarycurrency!")

                    yield {
                        'id': 'TRANSFER-{}'.format(activity['resource']['id']),
                        'datetime': created,
                        'amount': amount * negatizer,
                        'feeamount': 0,  # XXX!
                        'transtype': 'TRANSFER',
                        'paymentref': reference,
                        'fulldescription': fulldescription,
                    }
                elif activity['type'] in ('BALANCE_CASHBACK', 'CARD_CASHBACK'):
                    # No API endpoint to get this so we have to parse it out of
                    # a ridiculously formatted field.

                    parsed_amount, currency = self.parse_transferwise_amount(activity['primaryAmount'])
                    if currency != settings.CURRENCY_ABBREV:
                        # This is cashback in a different currency, so ignore it
                        continue

                    yield {
                        'id': '{}-{}'.format(activity['type'], activity['resource']['id']),
                        'datetime': activity['updatedOn'],
                        'amount': parsed_amount,
                        'feeamount': 0,
                        'transtype': activity['type'],
                        'paymentref': '',
                        'fulldescription': activity['type'].title().replace('_', ' '),
                    }
                elif activity['type'] == 'CARD_PAYMENT':
                    # For card payments, normal tokens appear not to have permissions
                    # to view the details, so try to parse it out of the activity.
                    parsed_amount, currency = self.parse_transferwise_amount(activity['primaryAmount'])
                    if currency != settings.CURRENCY_ABBREV:
                        # This is cashback in a different currency, so ignore it
                        continue

                    yield {
                        'id': 'CARD-{}'.format(activity['resource']['id']),
                        'datetime': activity['updatedOn'],
                        'amount': -parsed_amount,
                        'feeamount': 0,
                        'transtype': 'CARD',
                        'paymentref': '',
                        'fulldescription': 'Card payment: {}'.format(self.strip_tw_tags(activity['title']),),
                    }
                elif activity['type'] == 'INTERBALANCE':
                    yield {
                        'id': None,
                        'message': "Received INTERBALANCE transaction, details are not fully parsable so please handle manually. Contents: {}".format(activity),
                    }
                elif activity['type'] == 'CARD_CHECK':
                    # This is just a check that the card is OK, no money in the transaction
                    continue
                else:
                    print(activity)
                    raise Exception("Unhandled activity type {}".format(activity['type']))

            cursor = r.get('cursor', None)
            if not cursor:
                return

    def parse_transferwise_amount(self, amount):
        # Try to parse the really weird strings that they use as amount
        # Example: 'primaryAmount': '<positive>+ 5.10 EUR</positive>',
        m = re.match(r'^<positive>\+\s+([\d\.]+)\s+(\w+)</positive>$', amount.replace(',', ''))
        if m:
            return Decimal(m.group(1)).quantize(Decimal('0.01')), m.group(2)

        # Sometimes <positive> isn't there... Because.. Well it's not.
        m = re.match(r'^([\d\.]+)\s+(\w+)$', amount.replace(',', ''))
        if m:
            return Decimal(m.group(1)).quantize(Decimal('0.01')), m.group(2)

        raise Exception("Failed to parse transferwise amount from '{}'".format(amount))

    def strip_tw_tags(self, s):
        return re.subn('</?(strong|positive|negative|strikethrough)>', '', s)[0]

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

        # We can no longer fund the transfer, because Wise decided it's not allowed to access our own money.
        # So we have to tell the user to do it.

        # Fund the transfer from our account
#        fund = self.post(
#            'profiles/{}/transfers/{}/payments'.format(self.get_profile(), transferid),
#            {
#                'type': 'BALANCE',
#            },
#            version='v3',
#        )

        send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                         self.pm.config('notification_receiver'),
                         'TransferWise payout initiated!',
                         """A TransferWise payout of {0} with reference {1}
has been initiated. Unfortunately, it can not be completed
through the API due to restrictions at TransferWise, so you need to
log into the account and confirm it manually.

OPlease do so as soon as possible.
""".format(amount, reference))

        return (accid, quoteid, transferid)
