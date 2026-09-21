from django import forms
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.conf import settings
from django.utils import timezone

import datetime
from decimal import Decimal
import io
import json
import time
import uuid

from postgresqleu.util.widgets import StaticTextWidget, MonospaceTextarea
from postgresqleu.util.forms import SubmitButtonField
from postgresqleu.util.payment.banktransfer import BaseManagedBankPayment
from postgresqleu.util.payment.banktransfer import BaseManagedBankPaymentForm

import requests


class BackendQontoForm(BaseManagedBankPaymentForm):
    apiuser = forms.CharField(label='API user', required=True)
    apisecret = forms.CharField(label='API secret', required=True, widget=forms.widgets.PasswordInput(render_value=True))
    notification_receiver = forms.EmailField(required=True)
    notify_each_transaction = forms.BooleanField(required=False, help_text="Send an email notification for each transaction received")
    verify_balances = forms.BooleanField(required=False, help_text="Regularly verify that the account balance matches the accounting system")
    account = forms.ChoiceField(required=False, help_text='Select which account to map to. If none show in the list, try saving without and reopening the form.')
    connection = forms.CharField(label='Connection', required=False, widget=StaticTextWidget)

    config_readonly = ['connection', ]
    managed_fields = ['apiuser', 'apisecret', 'account', 'connection', 'notification_receiver', 'notify_each_transaction', 'verify_balances', ]
    managed_fieldsets = [
        {
            'id': 'qonto',
            'legend': 'Qonto',
            'fields': ['apiuser', 'apisecret', 'account'],
        },
        {
            'id': 'notifications',
            'legend': 'Notifications',
            'fields': ['notification_receiver', 'notify_each_transaction', 'verify_balances', ],
        },
        {
            'id': 'connection',
            'legend': 'Connection',
            'fields': ['connection', ],
        },
    ]

    def fix_fields(self):
        super().fix_fields()
        self.fields['feeaccount'].help_text = 'Currently no fees are fetched, so this account is a no-op'

        if 'apiuser' in self.instance.config:
            pm = self.instance.get_implementation()
            self.fields['account'].choices = pm.get_account_choices()
            self.initial['connection'] = 'Connected to Qonto account with user {}'.format(self.instance.config['apiuser'])

    def clean(self):
        d = super().clean()

        if d.get('active', False) and not d.get('account'):
            self.add_error('active', 'Cannot enable active until an account has explicitly been selected')

        return d


class Qonto(BaseManagedBankPayment):
    backend_form_class = BackendQontoForm

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = requests.sessions.Session()
        self.session.headers.update({
            'Authorization': '{}:{}'.format(self.config('apiuser'), self.config('apisecret')),
        })

    @property
    def description(self):
        return self.config('description').replace("\n", '<br/>') if self.config('description') else ''

    def render_page(self, request, invoice):
        return render(request, 'invoices/genericbankpayment.html', {
            'invoice': invoice,
            'bankinfo': self.config('bankinfo'),
        })

    def get_account_choices(self):
        r = self.session.get('https://thirdparty.qonto.com/v2/bank_accounts', timeout=10)
        if r.status_code != 200:
            return []

        return [(a['id'], a['iban']) for a in r.json()['bank_accounts'] if a['currency'] == settings.CURRENCY_ABBREV and a['status'] == 'active']

    def get_account_balance(self):
        r = self.session.get('https://thirdparty.qonto.com/v2/bank_accounts/{}'.format(self.config('account')), timeout=10)
        r.raise_for_status()

        return Decimal(r.json()['bank_account']['balance'])

    def fetch_transactions(self):
        notes = io.StringIO()

        params = {
            'bank_account_id': self.config('account'),
            'status': ['completed', ],
            'sort_by': 'created_at:asc',
        }
        start_date = self.method.config.get('last_sync_date', None)
        if start_date:
            # Always look one week back in time in case things somehow show up late
            params['created_at_from'] = datetime.date.fromisoformat(start_date) - datetime.timedelta(7)

        r = self.session.get('https://thirdparty.qonto.com/v2/transactions', params=params, timeout=30)
        r.raise_for_status()

        transactions = [
            {k: t.get(k, None) for k in ['id', 'amount', 'side', 'created_at', 'operation_type', 'reference', 'income']}
            for t in r.json()['transactions'] if t['currency'] == settings.CURRENCY_ABBREV
        ]

        self.method.config['last_sync_time'] = timezone.now().isoformat()
        self.method.save(update_fields=['config', ])

        return transactions
