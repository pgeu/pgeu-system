from django.core.exceptions import ValidationError
from django import forms
from django.template import Template, Context
from urllib.parse import urlencode

from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.backendforms import BackendInvoicePaymentMethodForm

from decimal import Decimal

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
    template = forms.CharField(required=True, widget=forms.widgets.Textarea,
                               validators=[validate_django_template, ],
                               help_text="Full django template for bank transfer page. Usually inherits one of the base templates, but can skip that if wanted.",
    )

    config_fields = ['template', ]
    config_fieldsets = [
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
