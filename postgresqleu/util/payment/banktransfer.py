from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django import forms
from django.db.models import Sum
from django.template import Template, Context
from django.shortcuts import render
from django.utils.functional import cached_property
from django.utils import timezone
from django.conf import settings

from urllib.parse import urlencode

from postgresqleu.util.db import exec_to_scalar
from postgresqleu.util.widgets import MonospaceTextarea, PrettyPrintJsonWidget
from postgresqleu.accounting.util import get_account_choices
from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.models import BankTransferFees
from postgresqleu.invoices.models import BankStatementRow
from postgresqleu.invoices.backendforms import BackendInvoicePaymentMethodForm
from postgresqleu.invoices.util import diff_workdays

from decimal import Decimal
import os.path
import json
import itertools

from . import BasePayment
from .bankfile import BankFileParser


def validate_django_template(value):
    try:
        t = Template(value)
        t.render(Context({
            'title': "Test title",
            'amount': Decimal(12.34),
        }))
    except Exception as e:
        raise ValidationError("Could not render template: {}".format(e))


class BackendBanktransferForm(BackendInvoicePaymentMethodForm):
    bankinfo = forms.CharField(required=False, widget=MonospaceTextarea,
                               label="Bank transfer information",
                               help_text="Full bank transfer information. If specified, this will be included in PDF invoices automatically",
    )
    template = forms.CharField(required=True, widget=forms.widgets.Textarea,
                               validators=[validate_django_template, ],
                               help_text="Full django template for bank transfer page. Usually inherits one of the base templates, but can skip that if wanted.",
    )

    config_fields = ['template', 'bankinfo', ]
    config_fieldsets = [
        {
            'id': 'invoice',
            'legend': 'Invoicing',
            'fields': ['bankinfo', ],
        },
        {
            'id': template,
            'legend': 'Template',
            'fields': ['template', ]
        },
    ]


class Banktransfer(BasePayment):
    backend_form_class = BackendBanktransferForm
    description = """
Using this payment method, you can pay via a regular bank transfer
using IBAN. Note that this requires that you are able to make a
payment in {}, and requires you to cover all transfer charges.
""".format(settings.CURRENCY_ABBREV)

    def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
        param = {
            'prv': self.id,
            'invoice': invoiceid,
            'key': Invoice.objects.get(pk=invoiceid).recipient_secret,
        }
        if returnurl:
            param['ret'] = returnurl
        return "/invoices/banktransfer/?%s" % urlencode(param)

    def render_page(self, request, invoice):
        t = Template(self.config('template', 'NOT CONFIGURED'))
        return t.render(Context({
            'title': invoice.invoicestr,
            'amount': invoice.total_amount,
        }))


# Base class for all *managed* bank payments (note that the above is
# *unmanaged* bank payments)
class BaseManagedBankPayment(BasePayment):
    def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
        param = {
            'prv': self.id,
            'invoice': invoiceid,
            'key': Invoice.objects.get(pk=invoiceid).recipient_secret,
        }
        if returnurl:
            param['ret'] = returnurl
        return "/invoices/banktransfer/?%s" % urlencode(param)

    def payment_fees(self, invoice):
        return BankTransferFees.objects.filter(invoice=invoice).aggregate(Sum('fee'))['fee__sum'] or 0

    # Override availability for direct bank transfers. We hide it if the invoice will be
    # automatically canceled in less than <n> working days.
    unavailable_less_than_days = 4

    def available(self, invoice):
        if invoice.canceltime:
            if diff_workdays(timezone.now(), invoice.canceltime) < self.unavailable_less_than_days:
                return False
        return True

    def unavailable_reason(self, invoice):
        if invoice.canceltime:
            if diff_workdays(timezone.now(), invoice.canceltime) < self.unavailable_less_than_days:
                return "Since this invoice will be automatically canceled in less than {0} working days, it requires the use of a faster payment method.".format(self.unavailable_less_than_days)


class BaseManagedBankPaymentForm(BackendInvoicePaymentMethodForm):
    bank_file_uploads = False
    managed_fields = []
    managed_fieldsets = []

    bankaccount = forms.ChoiceField(required=True, choices=get_account_choices,
                                    label="Account",
                                    help_text="Accounting account that is a 1-1 match to this bank account")
    feeaccount = forms.ChoiceField(required=True, choices=get_account_choices,
                                   label="Fee account",
                                   help_text="Accounting account that receives any fees associated with payments")
    bankinfo = forms.CharField(required=False, widget=MonospaceTextarea,
                               label="Bank transfer information",
                               help_text="Full bank transfer information. If specified, this will be included in PDF invoices automatically",
    )
    file_upload_interval = forms.IntegerField(required=True,
                                              label="File upload interval",
                                              help_text="How often to request file uploads for this account, or zero if never",
                                              validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    def fix_fields(self):
        super(BaseManagedBankPaymentForm, self).fix_fields()
        if not self.bank_file_uploads:
            del self.fields['file_upload_interval']

    @property
    def config_fields(self):
        extra = []
        if self.bank_file_uploads:
            extra = ['file_upload_interval', ]

        return ['bankaccount', 'feeaccount', 'bankinfo', ] + self.managed_fields + extra

    @property
    def config_fieldsets(self):
        prep = []

        if self.bank_file_uploads:
            prep = [
                {
                    'id': 'management',
                    'legend': 'Management',
                    'fields': ['file_upload_interval', ]
                },
            ]

        return prep + [
            {
                'id': 'accounting',
                'legend': 'Accounting',
                'fields': ['bankaccount', 'feeaccount', ],
            },
            {
                'id': 'invoice',
                'legend': 'Invoicing',
                'fields': ['bankinfo', ],
            },
        ] + self.managed_fieldsets

    def clean_bankaccount(self):
        n = exec_to_scalar("SELECT count(1) FROM invoices_invoicepaymentmethod WHERE config->>'bankaccount' = %(account)s AND (id != %(self)s OR %(self)s IS NULL)", {
            'account': self.cleaned_data['bankaccount'],
            'self': self.instance.id,
        })
        if n > 0:
            raise ValidationError("This account is already managed by a different payment method!")
        return self.cleaned_data['bankaccount']


def _get_file_choices():
    def __get_file_choices():
        # Not so efficient, but for now, meh, it's backend config only
        for fn in os.listdir(os.path.join(os.path.dirname(__file__), 'fileproviders')):
            if fn.endswith('.json'):
                try:
                    with open(os.path.join(os.path.dirname(__file__), 'fileproviders', fn)) as f:
                        j = json.load(f)
                        yield (fn[:-5], j['name'], j['region'])
                except Exception:
                    pass
    for region, entries in itertools.groupby(sorted(__get_file_choices(), key=lambda x: (x[2], x[1])), lambda x: x[2]):
        yield (region, [e[0:2] for e in entries])
    yield ('Custom', (
        ('custom', 'Custom'),
    ))


class GenericManagedBankPaymentForm(BaseManagedBankPaymentForm):
    bank_file_uploads = True

    description = forms.CharField(required=True, widget=MonospaceTextarea,
                                  help_text='Text shown on page promting the user to select payment')

    filetype = forms.ChoiceField(required=True, choices=_get_file_choices(), label='Type',
                                 initial='custom',
                                 help_text='Select the provider of file to upload')
    definition = forms.CharField(required=False, widget=PrettyPrintJsonWidget,
                                 label='Definition',
                                 help_text='JSON format for field definition if custom')

    managed_fields = ['description', 'filetype', 'definition', ]
    managed_fieldsets = [
        {
            'id': 'importfile',
            'legend': 'Import file',
            'fields': ['filetype', 'definition', ],
        },
    ]

    json_fields = ['definition', ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for fn, f in self._validationfields:
            # Must be required=false so that we can save when changing type
            self.fields[f] = forms.CharField(required=False, label=fn)

    @cached_property
    def _validationfields(self):
        return list(self.__validationfields())

    @cached_property
    def _validationfieldnames(self):
        return [f for fn, f in self._validationfields]

    def __validationfields(self):
        if 'filetype' not in self.instance.config:
            # If we have no filetype set yet, we don't know about any extra fields
            return []

        if self.instance.config['filetype'] == 'custom':
            raise Exception("Custom!")
        else:
            with open(os.path.join(os.path.dirname(__file__), 'fileproviders', "{}.json".format(self.instance.config['filetype']))) as f:
                j = json.load(f)
        for c in j['columns']:
            if c['function'] == 'validate':
                yield (c['validate'], 'validate_{}'.format(c['header'][0].lower()))

    @property
    def config_fields(self):
        f = super().config_fields
        return f + self._validationfieldnames

    @property
    def config_fieldsets(self):
        f = super().config_fieldsets
        for ff in f:
            if ff['id'] == 'invoice':
                ff['fields'].append('description')
        if self._validationfields:
            f.append({
                'id': 'validation',
                'legend': 'Validation data',
                'fields': self._validationfieldnames,
            })
        return f

    def clean(self):
        c = super().clean()

        if self.cleaned_data['filetype'] == 'custom':
            if 'definition' in self.cleaned_data and not self.cleaned_data['definition']:
                self.add_error('definition', 'Definition must be specified when filetype is custom')
        else:
            if self.cleaned_data['definition']:
                self.add_error('definition', 'Definition must be empty when specific file provider is selected')
        return c

    def clean_definition(self):
        if self.cleaned_data['definition']:
            try:
                return json.loads(self.cleaned_data['definition'])
            except Exception as e:
                raise ValidationError("Not valid JSON: {}".format(e))
        return self.cleaned_data['definition']


class GenericManagedBankPayment(BaseManagedBankPayment):
    backend_form_class = GenericManagedBankPaymentForm

    def render_page(self, request, invoice):
        return render(request, 'invoices/genericbankpayment.html', {
            'invoice': invoice,
            'bankinfo': self.config('bankinfo'),
        })

    @cached_property
    def definition(self):
        if self.config('filetype') == 'custom':
            return json.loads(self.config('filetype'))
        else:
            try:
                with open(os.path.join(os.path.dirname(__file__), 'fileproviders', "{}.json".format(self.config('filetype')))) as f:
                    return json.load(f)
            except Exception:
                raise
                return {}

    @property
    def description(self):
        return self.config('description').replace("\n", '<br/>')

    @property
    def upload_tooltip(self):
        return self.definition.get('upload_tooltip', '').replace("\n", '<br/>')

    def parse_uploaded_file_to_rows(self, t):
        parser = BankFileParser(self.definition)
        return list(parser.parse(t))

    def convert_uploaded_file_to_utf8(self, f):
        return f.read().decode(self.definition['encoding'])

    def process_loaded_rows(self, rows):
        extrakeys = set()
        hasvaluefor = {
            'uniqueid': False,
            'balance': False,
        }
        anyerror = False

        for r in rows:
            r['row_already_exists'] = False
            if 'uniqueid' in r:
                # We can use the unique ID to find if this transaction already exists
                if BankStatementRow.objects.filter(method=self.method, uniqueid=r['uniqueid']).exists():
                    r['row_already_exists'] = True
            else:
                # We must match on the combination of date, amount and description since we have no unique id
                if BankStatementRow.objects.filter(method=self.method, date=r['date'], amount=r['amount'], description=r['text']).exists():
                    r['row_already_exists'] = True

            for k, v in r['validate'].items():
                if v['val'] != self.config('validate_{}'.format(k), None):
                    if 'row_errors' not in r:
                        r['row_errors'] = []
                    r['row_errors'].append('Field {} has invalid value'.format(k))
                    anyerror = True

            extrakeys.update(r['other'].keys())
            for k in hasvaluefor.keys():
                if k in r:
                    hasvaluefor[k] = True

        return (anyerror, extrakeys, hasvaluefor)
