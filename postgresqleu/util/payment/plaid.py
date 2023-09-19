from django import forms
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.conf import settings

import io
import json

from postgresqleu.util.widgets import StaticTextWidget, MonospaceTextarea
from postgresqleu.util.forms import SubmitButtonField
from postgresqleu.util.payment.banktransfer import BaseManagedBankPayment
from postgresqleu.util.payment.banktransfer import BaseManagedBankPaymentForm
from postgresqleu.mailqueue.util import send_simple_mail

import requests


class BackendPlaidForm(BaseManagedBankPaymentForm):
    description = forms.CharField(required=True, widget=MonospaceTextarea,
                                  help_text='Text shown on page promting the user to select payment')
    clientid = forms.CharField(label='Client ID', required=True)
    secret = forms.CharField(required=True, widget=forms.widgets.PasswordInput(render_value=True))
    notification_receiver = forms.EmailField(required=True)
    notify_each_transaction = forms.BooleanField(required=False, help_text="Send an email notification for each transaction received")
    verify_balances = forms.BooleanField(required=False, help_text="Regularly verify that the account balance matches the accounting system")
    connect = SubmitButtonField(label="Connect to plaid", required=False)
    connection = forms.CharField(label='Connection', required=False, widget=StaticTextWidget)
    reconnect = SubmitButtonField(label="Refresh connection to plaid", required=False)

    config_readonly = ['connect', 'connection', 'reconnect', ]
    managed_fields = ['description', 'clientid', 'secret', 'connect', 'connection', 'reconnect', 'notification_receiver', 'notify_each_transaction', 'verify_balances', ]
    managed_fieldsets = [
        {
            'id': 'plaid',
            'legend': 'Plaid',
            'fields': ['clientid', 'secret', ],
        },
        {
            'id': 'notifications',
            'legend': 'Notifications',
            'fields': ['notification_receiver', 'notify_each_transaction', 'verify_balances', ],
        },
        {
            'id': 'connection',
            'legend': 'Connection',
            'fields': ['connect', 'connection', 'reconnect', ],
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
        self.fields['feeaccount'].help_text = 'Currently no fees are fetched4, so this account is a no-op'

        if 'accountid' in self.instance.config:
            self.initial['connection'] = 'Connected to plaid account <code>{}</code>.'.format(self.instance.config['accountid'])
            self.fields['connect'].widget.label = "Already connected"
            self.fields['connect'].widget.attrs['disabled'] = True
            self.fields['reconnect'].callback = self.refresh_plaid_connect
        else:
            self.fields['connect'].callback = self.connect_to_plaid
            self.initial['connection'] = 'Not connected.'
            self.fields['reconnect'].widget.label = 'Not connected'
            self.fields['reconnect'].widget.attrs['disabled'] = True

        if not self.instance.config.get('clientid', None) or not self.instance.config.get('secret', None):
            self.fields['connect'].widget.attrs['disabled'] = True
            self.fields['connect'].help_text = "Save the client and secret id before you can connect to plaid"

    def connect_to_plaid(self, request):
        return HttpResponseRedirect("plaidconnect/")

    def refresh_plaid_connect(self, request):
        return HttpResponseRedirect("refreshplaidconnect/")


class Plaid(BaseManagedBankPayment):
    backend_form_class = BackendPlaidForm
    ROOTURL = 'https://{}.plaid.com/'.format(settings.PLAID_LEVEL)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = requests.sessions.Session()
        self.session.headers.update({
            'PLAID-CLIENT-ID': self.method.config.get('clientid', ''),
            'PLAID-SECRET': self.method.config.get('secret', ''),
        })

    @property
    def description(self):
        return self.config('description').replace("\n", '<br/>') if self.config('description') else ''

    def render_page(self, request, invoice):
        return render(request, 'invoices/genericbankpayment.html', {
            'invoice': invoice,
            'bankinfo': self.config('bankinfo'),
        })

    def get_link_token(self, previous_accesstoken=None):
        payload = {
            'client_name': settings.ORG_NAME,
            'language': 'en',
            'country_codes': settings.PLAID_COUNTRIES,
            'user': {
                'client_user_id': str(self.method.id),
            },
            'products': ['transactions', ],
            'webhook': '{}/wh/plaid/{}/'.format(settings.SITEBASE, self.method.id),
        }
        if previous_accesstoken:
            payload['access_token'] = previous_accesstoken

        r = self.session.post('{}link/token/create'.format(self.ROOTURL), json=payload, timeout=10)
        if r.status_code != 200:
            return None
        return r.json()['link_token']

    def exchange_token(self, public_token):
        r = self.session.post('{}item/public_token/exchange'.format(self.ROOTURL), json={
            'public_token': public_token,
        }, timeout=10)
        if r.status_code != 200:
            return None
        return r.json()['access_token']

    def disconnect(self):
        self.session.post('{}/item/remove'.format(self.ROOTURL), json={
            'access_token': self.method.config.get('access_token', ''),
        }, timeout=10)

    def get_account_balances(self):
        r = self.session.post('{}auth/get'.format(self.ROOTURL), json={
            'access_token': self.method.config.get('access_token', ''),
        }, timeout=10)
        if r.status_code != 200:
            return []

        return [
            {
                'accountid': a['account_id'],
                'balance': a['balances']['current'],
                'currency': a['balances']['iso_currency_code'],
            } for a in r.json()['accounts']
        ]

    def get_signing_key(self, current_key_id):
        cache = self.method.config.get('signing_key_cache', {})
        if current_key_id in cache:
            return cache[current_key_id]

        # Refresh our cache of keys
        keys_ids_to_update = [key_id for key_id, key in cache.items()
                              if key['expired_at'] is None]
        keys_ids_to_update.append(current_key_id)

        newcache = {}
        for key_id in keys_ids_to_update:
            r = self.session.post('{}webhook_verification_key/get'.format(self.ROOTURL), json={
                'key_id': key_id
            }, timeout=8)
            if r.status_code != 200:
                continue
            newcache[key_id] = r.json()['key']

        self.method.config['signing_key_cache'] = newcache
        self.method.save(update_fields=['config', ])

        return newcache.get(current_key_id, None)

    def sync_transactions(self):
        # Sync transactions from plaid.
        # ONLY added transactions supported at this point. Anything under removed or changed will be turned
        # into an email notification only.
        if 'access_token' not in self.method.config:
            print("No access token, exiting")
            return []

        notes = io.StringIO()
        initial_cursor = self.method.config.get('sync_cursor', None)

        param = {
            'access_token': self.method.config['access_token'],
            'count': 100,
        }

        transactions = []
        while True:
            if 'sync_cursor' in self.method.config:
                param['cursor'] = self.method.config['sync_cursor']

            r = self.session.post('{}transactions/sync'.format(self.ROOTURL), json=param)
            r.raise_for_status()

            j = r.json()
            for t in j['added']:
                if t['iso_currency_code'] != settings.CURRENCY_ISO:
                    notes.write("Transaction {}, description '{}', has invalid currency {}.\n".format(t['transaction_id'], t['name'], t['iso_currency_code']))
                if t['account_id'] != self.method.config['accountid']:
                    notes.write("Transaction {}, description '{}', is on account {}, but we only know about {}.\n".format(
                        t['transaction_id'], t['name'], t['account_id'], self.method.config['accountid'],
                    ))
            for t in j['modified']:
                notes.write("Transaction modification entry for {}, can't process.\n".format(t['transaction_id']))
                notes.write("{}\n----\n".format(json.dumps(t)))
            for t in j['removed']:
                notes.write("Transaction {} removed, can't process.\n".format(t['transaction_id']))
                notes.write("{}\n----\n".format(json.dumps(t)))

            transactions.extend([t for t in j['added'] if t['iso_currency_code'] == settings.CURRENCY_ISO and t['account_id'] == self.method.config['accountid']])

            self.method.config['sync_cursor'] = j['next_cursor']

            if not j.get('has_more', False):
                break
            # if we have more, we loop up to get more

        if initial_cursor != self.method.config['sync_cursor']:
            self.method.save(update_fields=['config'])

        if notes.tell():
            # Some notes were generated. We don't have a good way to handle this, so we're just going to generate an email with it...
            send_simple_mail(
                settings.INVOICE_SENDER_EMAIL,
                self.method.config['notification_receiver'],
                "Plaid transaction fetch notices for {}".format(self.method.internaldescription),
                "Fetching plaid transactions for {} resulted in some noties:\n\n{}\n".format(
                    self.method.internaldescription,
                    notes.getvalue(),
                ),
            )

        return transactions
