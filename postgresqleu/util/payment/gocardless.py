from django import forms
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.conf import settings

import datetime
from decimal import Decimal
import io
import json
import time

from postgresqleu.util.widgets import StaticTextWidget, MonospaceTextarea
from postgresqleu.util.forms import SubmitButtonField
from postgresqleu.util.payment.banktransfer import BaseManagedBankPayment
from postgresqleu.util.payment.banktransfer import BaseManagedBankPaymentForm
from postgresqleu.mailqueue.util import send_simple_mail

import requests


class BackendGocardlessForm(BaseManagedBankPaymentForm):
    description = forms.CharField(required=True, widget=MonospaceTextarea,
                                  help_text='Text shown on page promting the user to select payment')
    secretid = forms.CharField(label='Secret ID', required=True)
    secretkey = forms.CharField(label='Secret key', required=True, widget=forms.widgets.PasswordInput(render_value=True))
    notification_receiver = forms.EmailField(required=True)
    notify_each_transaction = forms.BooleanField(required=False, help_text="Send an email notification for each transaction received")
    verify_balances = forms.BooleanField(required=False, help_text="Regularly verify that the account balance matches the accounting system")
    connect = SubmitButtonField(label="Connect to gocardless", required=False)
    connection = forms.CharField(label='Connection', required=False, widget=StaticTextWidget)

    config_readonly = ['connect', 'connection', ]
    managed_fields = ['description', 'secretid', 'secretkey', 'connect', 'connection', 'notification_receiver', 'notify_each_transaction', 'verify_balances', ]
    managed_fieldsets = [
        {
            'id': 'gocardless',
            'legend': 'Gocardless',
            'fields': ['secretid', 'secretkey', ],
        },
        {
            'id': 'notifications',
            'legend': 'Notifications',
            'fields': ['notification_receiver', 'notify_each_transaction', 'verify_balances', ],
        },
        {
            'id': 'connection',
            'legend': 'Connection',
            'fields': ['connect', 'connection', ],
        },
    ]

    @property
    def config_fieldsets(self):
        f = super().config_fieldsets
        for ff in f:
            if ff['id'] == 'invoice':
                ff['fields'].append('description')
        return f

    def fix_fields(self):
        super().fix_fields()
        self.fields['feeaccount'].help_text = 'Currently no fees are fetched, so this account is a no-op'

        if 'accountid' in self.instance.config:
            self.initial['connection'] = 'Connected to gocardless account id {}.'.format(self.instance.config['accountid'])
            self.fields['connect'].widget.label = "Already connected"
            self.fields['connect'].widget.attrs['disabled'] = True
        else:
            self.fields['connect'].callback = self.connect_to_provider
            self.initial['connection'] = 'Not connected.'

        if not self.instance.config.get('secretid', None) or not self.instance.config.get('secretkey', None):
            self.fields['connect'].widget.attrs['disabled'] = True
            self.fields['connect'].help_text = "Save the secret id and key before you can connect to gocardless"

    def connect_to_provider(self, request):
        return HttpResponseRedirect("gocardlessconnect/")


class Gocardless(BaseManagedBankPayment):
    backend_form_class = BackendGocardlessForm

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = requests.sessions.Session()
        self.session.headers.update({
            'Authorization': 'Bearer {}'.format(self._get_access_token()),
        })

    @property
    def description(self):
        return self.config('description').replace("\n", '<br/>') if self.config('description') else ''

    def render_page(self, request, invoice):
        return render(request, 'invoices/genericbankpayment.html', {
            'invoice': invoice,
            'bankinfo': self.config('bankinfo'),
        })

    def _get_access_token(self):
        if 'access_token' in self.method.config:
            if self.method.config.get('access_token_expires_at', 0) < time.time() + 120:
                # Access token expires in the next 120 seconds, then we try to refresh it it,
                # if we have a refresh token valid at least 4 hours (otherwise not much point)
                if self.method.config.get('refresh_token_expires_at', 0) > time.time() + (4 * 60 * 60):
                    r = requests.post('https://bankaccountdata.gocardless.com/api/v2/token/refresh/', json={
                        'refresh': self.method.config['refresh_token'],
                    }, timeout=10)
                    if r.status_code == 200:
                        j = r.json()
                        self.method.config.update({
                            'access_token': j['access'],
                            'access_token_expires_at': int(time.time() + j['access_expires']),
                        })
                        self.method.save(update_fields=['config', ])
                        return j['access']
                    # Else we failed to get a refresh token. So zap our existing access
                    # token, to get a brand new try next time.
                    del self.method.config['access_token']
                    del self.method.config['access_token_expires_at']
                    self.method.save(update_fields=['config'])
                    # Now fall through to request a new token
                # If we don't have a refresh one, also fall through and request a new one
            else:
                return self.method.config['access_token']
        # Request a new access token
        r = requests.post('https://bankaccountdata.gocardless.com/api/v2/token/new/', json={
            'secret_id': self.method.config['secretid'],
            'secret_key': self.method.config['secretkey'],
        }, timeout=10)
        r.raise_for_status()

        j = r.json()
        self.method.config.update({
            'access_token': j['access'],
            'access_token_expires_at': int(time.time() + j['access_expires']),
            'refresh_token': j['refresh'],
            'refresh_token_expires_at': int(time.time() + j['refresh_expires']),
        })
        self.method.save(update_fields=['config', ])

        return j['access']

    def _account_url(self, suburl):
        return 'https://bankaccountdata.gocardless.com/api/v2/accounts/{}/{}/'.format(
            self.method.config.get('accountid'),
            suburl,
        )

    def _check_api_status(self, r):
        if r.status_code >= 200 and r.status_code < 300:
            return
        # Maybe do some nicer parsing of errors here at some point
        raise Exception("Http status {}, body {}".format(r.status_code, r.text))

    def get_banks_in_country(self, countrycode):
        r = self.session.get('https://bankaccountdata.gocardless.com/api/v2/institutions/', params={'country': countrycode.lower()}, timeout=10)
        self._check_api_status(r)
        return r.json()

    def get_bank_connection_link(self, bank):
        # Start by creating an EUA for 180 days, since we can instead of the default 90 days
        r = self.session.post('https://bankaccountdata.gocardless.com/api/v2/agreements/enduser/', json={
            'institution_id': bank,
            'access_valid_for_days': '180',
            'access_scope': ['balances', 'details', 'transactions'],
        }, timeout=20)
        self._check_api_status(r)

        # Then create the requisitions
        rr = self.session.post('https://bankaccountdata.gocardless.com/api/v2/requisitions/', json={
            'redirect': '{}/admin/invoices/paymentmethods/{}/gocardlessconnect/'.format(
                settings.SITEBASE,
                self.method.id,
            ),
            'institution_id': bank,
            'reference': str(self.method.id),
            'agreement': r.json()['id'],
            'user_language': 'EN',
        }, timeout=20)
        self._check_api_status(r)

        # Before we return the link, we have to store the requisition id, as that's what we'll use to
        # access accounts!
        self.method.config['requisition'] = rr.json()['id']
        self.method.save(update_fields=['config'])

        return rr.json()['link']

    def finalize_bank_setup(self):
        # Try to find an account
        if 'requisition' not in self.method.config:
            raise Exception('Requisition not stored on this method, should not get here.')

        r = self.session.get('https://bankaccountdata.gocardless.com/api/v2/requisitions/{}/'.format(self.method.config['requisition']), timeout=30)
        self._check_api_status(r)

        account = r.json()['accounts'][0]
        self.method.config['accountid'] = account
        self.method.save(update_fields=['config', ])

    def get_account_balance(self):
        r = self.session.get(self._account_url('balances'), timeout=30)
        if r.status_code != 200:
            return []

        j = r.json()
        balances = [b for b in j['balances'] if b['balanceAmount']['currency'] == settings.CURRENCY_ISO]

        if not balances:
            raise Exception("No balances in currency {} found".format(settings.CURRENCY_ISO))

        if len(j['balances']) == 1:
            return Decimal(balances[0]['balanceAmount']['amount'])

        # closingBooked is what we get on Credit Mutuel, it's uncertain if that comes from
        # them or from gocardless... But for now, assume.
        for b in balances:
            if b['balanceType'] == 'closingBooked':
                return Decimal(b['balanceAmount']['amount'])

        raise Exception("Multiple balances returned, don't know which one to use")

    def fetch_transactions(self):
        notes = io.StringIO()

        params = {}
        start_date = self.method.config.get('last_sync_date', None)
        if start_date:
            # Always look one week back in time in case things somehow show up late
            params['date_from'] = datetime.date.fromisoformat(start_date) - datetime.timedelta(7)

        r = self.session.get(self._account_url('transactions'), timeout=30)
        self._check_api_status(r)

        transactions = r.json()['transactions']['booked']

        # Do some sanity checking
        for t in transactions:
            if t['transactionAmount']['currency'] != settings.CURRENCY_ISO:
                raise Exception("Invalid currency {}, expected {}".format(
                    t['transactionAmount']['currency'],
                    settings.CURRENCY_ISO,
                ))

        self.method.config['last_sync_date'] = str(datetime.date.today())
        self.method.save(update_fields=['config', ])

        return transactions
