from django import forms
from django.conf import settings

from postgresqleu.util.widgets import StaticTextWidget
from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.backendforms import BackendInvoicePaymentMethodForm
from postgresqleu.accounting.util import get_account_choices
from postgresqleu.stripepayment.models import StripeCheckout
from postgresqleu.stripepayment.api import StripeApi

from . import BasePayment


class BackendStripeForm(BackendInvoicePaymentMethodForm):
    published_key = forms.CharField(required=True, label="Publishable key")
    secret_key = forms.CharField(required=True, label="Secret key",
                                 widget=forms.widgets.PasswordInput(render_value=True))
    webhook_secret = forms.CharField(required=True, label="Webhook secret key",
                                     widget=forms.widgets.PasswordInput(render_value=True),
                                     help_text="See below under Stripe configuration for details on how to configure.")
    notification_receiver = forms.EmailField(required=True)
    accounting_income = forms.ChoiceField(required=True, choices=get_account_choices,
                                          label="Completed payments account")
    accounting_fee = forms.ChoiceField(required=True, choices=get_account_choices,
                                       label="Fees account")
    accounting_payout = forms.ChoiceField(required=True, choices=get_account_choices,
                                          label="Payout account")
    verify_balances = forms.BooleanField(required=False, help_text="Regularly verify that the account balance matches the accounting system")
    webhook = forms.CharField(label='Webhook', widget=StaticTextWidget)

    config_fields = ['notification_receiver', 'published_key', 'secret_key', 'webhook_secret',
                     'accounting_income', 'accounting_fee', 'accounting_payout', 'verify_balances']
    config_readonly = ['webhook', ]

    config_fieldsets = [
        {
            'id': 'stripe',
            'legend': 'Stripe',
            'fields': ['notification_receiver', 'published_key', 'secret_key', 'webhook_secret', ],
        },
        {
            'id': 'accounting',
            'legend': 'Accounting',
            'fields': ['accounting_income', 'accounting_fee', 'accounting_payout', 'verify_balances'],
        },
        {
            'id': 'stripeconf',
            'legend': 'Stripe configuration',
            'fields': ['webhook', ],
        }
    ]

    def fix_fields(self):
        super(BackendStripeForm, self).fix_fields()
        if self.instance.id:
            self.initial.update({
                'webhook': """
From the Stripe dashboard, go to Webhooks and add an endpoint that points to
<code>{0}/p/stripe/{1}/webhook/</code>. This webhook should receive events of
types <b>checkout.session.completed</b>, <b>charge.refunded</b> and
<b>payout.paid</b>.
Copy the key from this webhook into the <i>webhook secret</i> field above.""".format(
                    settings.SITEBASE,
                    self.instance.id),
            })


class Stripe(BasePayment):
    backend_form_class = BackendStripeForm
    description = """
Using this payment method, you can pay using your credit card, including
Mastercard, VISA and American Express.
"""

    def __init__(self, *args, **kwargs):
        super(Stripe, self).__init__(*args, **kwargs)

    def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
        i = Invoice.objects.get(pk=invoiceid)
        return '/invoices/stripepay/{0}/{1}/{2}/'.format(self.id, invoiceid, i.recipient_secret)

    def payment_fees(self, invoice):
        co = StripeCheckout.objects.get(invoiceid=invoice.id)
        return co.fee

    def used_method_details(self, invoice):
        co = StripeCheckout.objects.get(invoiceid=invoice.id)
        return "Credit Card ({0})".format(co.paymentmethod)

    def autorefund(self, refund):
        co = StripeCheckout.objects.get(invoiceid=refund.invoice.id)

        api = StripeApi(self)
        refund.payment_reference = api.refund_transaction(co, refund.fullamount, refund.id)

        return True
