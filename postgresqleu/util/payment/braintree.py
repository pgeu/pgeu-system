from django import forms

import re

from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.backendforms import BackendInvoicePaymentMethodForm
from postgresqleu.accounting.util import get_account_choices
from postgresqleu.braintreepayment.models import BraintreeTransaction

from . import BasePayment


class BackendBraintreeForm(BackendInvoicePaymentMethodForm):
    sandbox = forms.BooleanField(required=False, label="Use testing sandbox")
    merchantid = forms.CharField(required=True, label="Merchant ID",
                                 help_text="From Account -> Merchant Account Info")
    notification_receiver = forms.EmailField(required=True)
    public_key = forms.CharField(required=True, label="Public key",
                                 help_text="From Settings -> API Keys")
    private_key = forms.CharField(required=True, label="Private key",
                                  help_text="From Settings -> API Keys",
                                  widget=forms.widgets.PasswordInput(render_value=True))
    accounting_authorized = forms.ChoiceField(required=True, choices=get_account_choices,
                                              label="Authorized payments account")
    accounting_payable = forms.ChoiceField(required=True, choices=get_account_choices,
                                           label="Payable balance account")
    accounting_fee = forms.ChoiceField(required=True, choices=get_account_choices,
                                       label="Fees account")
    accounting_payout = forms.ChoiceField(required=True, choices=get_account_choices,
                                          label="Payout account")

    config_fields = ['sandbox', 'merchantid', 'notification_receiver', 'public_key', 'private_key',
                     'accounting_authorized', 'accounting_payable', 'accounting_fee', 'accounting_payout']

    config_fieldsets = [
        {
            'id': 'braintree',
            'legend': 'Braintree',
            'fields': ['merchantid', 'notification_receiver', 'sandbox', 'public_key', 'private_key', ],
        },
        {
            'id': 'accounting',
            'legend': 'Accounting',
            'fields': ['accounting_authorized', 'accounting_payable', 'accounting_fee', 'accounting_payout'],
        }
    ]


class Braintree(BasePayment):
    backend_form_class = BackendBraintreeForm
    description = """
Using this payment method, you can pay using your credit card, including
Mastercard, VISA and American Express.
"""

    def __init__(self, *args, **kwargs):
        super(Braintree, self).__init__(*args, **kwargs)
        try:
            globals()["braintree"] = __import__("braintree")
            self.braintree_ok = True
            self.braintree_initialized = False
        except ImportError:
            self.braintree_ok = False

    def build_payment_url(self, invoicestr, invoiceamount, invoiceid, returnurl=None):
        i = Invoice.objects.get(pk=invoiceid)
        if i.recipient_secret:
            return "/invoices/braintree/{0}/{1}/{2}/".format(self.id, invoiceid, i.recipient_secret)
        else:
            return "/invoices/braintree/{0}/{1}/".format(self.id, invoiceid)

    _re_braintree = re.compile('^Braintree id ([a-z0-9]+)$')

    def _find_invoice_transaction(self, invoice):
        m = self._re_braintree.match(invoice.paymentdetails)
        if m:
            try:
                return (BraintreeTransaction.objects.get(transid=m.groups(1)[0]), None)
            except BraintreeTransaction.DoesNotExzist:
                return (None, "not found")
        else:
            return (None, "unknown format")

    def payment_fees(self, invoice):
        (trans, reason) = self._find_invoice_transaction(invoice)
        if not trans:
            return reason
        if trans.disbursedamount:
            return trans.amount - trans.disbursedamount
        else:
            return "not disbursed yet"

    def used_method_details(self, invoice):
        (trans, reason) = self._find_invoice_transaction(invoice)
        if not trans:
            raise Exception(reason)
        return "Credit Card ({0})".format(trans.method)

    def available(self, invoice):
        return self.braintree_ok

    def unavailable_reason(self, invoice):
        if not self.braintree_ok:
            return "Unable to load processing module"

    def initialize_braintree(self):
        if self.braintree_initialized:
            return

        braintree.Configuration.configure(
            self.config('sandbox') and braintree.Environment.Sandbox or braintree.Environment.Production,
            self.config('merchantid'),
            self.config('public_key'),
            self.config('private_key'),
        )
        self.braintree_initialized = True

    def generate_client_token(self):
        self.initialize_braintree()
        return braintree.ClientToken.generate({})

    def braintree_sale(self, options):
        self.initialize_braintree()
        return braintree.Transaction.sale(options)

    def braintree_find(self, transid):
        self.initialize_braintree()
        try:
            return (True, braintree.Transaction.find(transid))
        except braintree.exceptions.not_found_error.NotFoundError as ex:
            return (False, ex)
