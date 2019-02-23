from django.core.exceptions import ValidationError
from django import forms
from django.db.models import Sum
from django.template import Template, Context
from urllib.parse import urlencode

from postgresqleu.util.db import exec_to_scalar
from postgresqleu.accounting.util import get_account_choices
from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.models import BankTransferFees
from postgresqleu.invoices.backendforms import BackendInvoicePaymentMethodForm
from postgresqleu.invoices.util import diff_workdays

from decimal import Decimal
from datetime import datetime

from . import BasePayment


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
    bankinfo = forms.CharField(required=False, widget=forms.widgets.Textarea,
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
payment in Euros, and requires you to cover all transfer charges.
"""

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
            if diff_workdays(datetime.now(), invoice.canceltime) < self.unavailable_less_than_days:
                return False
        return True

    def unavailable_reason(self, invoice):
        if invoice.canceltime:
            if diff_workdays(datetime.now(), invoice.canceltime) < self.unavailable_less_than_days:
                return "Since this invoice will be automatically canceled in less than {0} working days, it requires the use of a faster payment method.".format(self.unavailable_less_than_days)


class BaseManagedBankPaymentForm(BackendInvoicePaymentMethodForm):
    bankaccount = forms.ChoiceField(required=True, choices=get_account_choices,
                                    label="Account",
                                    help_text="Accounting account that is a 1-1 match to this bank account")
    feeaccount = forms.ChoiceField(required=True, choices=get_account_choices,
                                   label="Fee account",
                                   help_text="Accounting account that receives any fees associated with payments")
    bankinfo = forms.CharField(required=False, widget=forms.widgets.Textarea,
                               label="Bank transfer information",
                               help_text="Full bank transfer information. If specified, this will be included in PDF invoices automatically",
    )

    @property
    def config_fields(self):
        return ['bankaccount', 'feeaccount', 'bankinfo', ] + self.managed_fields

    @property
    def config_fieldsets(self):
        return [
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
