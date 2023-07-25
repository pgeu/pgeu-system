from django import forms
from django.core.validators import MinValueValidator
from django.contrib import messages
from django.shortcuts import render
from django.conf import settings

import re
import uuid
from io import StringIO

from postgresqleu.util.payment.banktransfer import BaseManagedBankPayment
from postgresqleu.util.payment.banktransfer import BaseManagedBankPaymentForm
from postgresqleu.util.forms import SubmitButtonField
from postgresqleu.util.widgets import MonospaceTextarea, StaticTextWidget
from postgresqleu.util.crypto import validate_pem_public_key, validate_pem_private_key
from postgresqleu.util.crypto import generate_rsa_keypair
from postgresqleu.accounting.util import get_account_choices
from postgresqleu.transferwise.api import TransferwiseApi

from postgresqleu.transferwise.models import TransferwiseTransaction, TransferwisePayout


class BackendTransferwiseForm(BaseManagedBankPaymentForm):
    apikey = forms.CharField(required=True, widget=forms.widgets.PasswordInput(render_value=True))
    public_key = forms.CharField(required=False, widget=MonospaceTextarea, validators=[validate_pem_public_key, ])
    private_key = forms.CharField(required=False, widget=MonospaceTextarea, validators=[validate_pem_private_key, ])
    generatekey = SubmitButtonField(label="Generate new keypair", required=False)
    canrefund = forms.BooleanField(required=False, label='Can refund',
                                   help_text='Process automatic refunds. This requires an API key with full access to make transfers to any accounts')
    autopayout = forms.BooleanField(required=False, label='Automatic payouts',
                                    help_text='Issue automatic payouts when account balances goes above a specified level.')
    autopayouttrigger = forms.IntegerField(required=False, label='Payout trigger',
                                           validators=[MinValueValidator(1), ],
                                           help_text='Trigger automatic payouts when balance goes above this')
    autopayoutlimit = forms.IntegerField(required=False, label='Payout limit',
                                         validators=[MinValueValidator(0), ],
                                         help_text='When issuing automatic payouts, keep this amount in the account after the payout is done')
    autopayoutname = forms.CharField(required=False, max_length=64, label='Recipent name',
                                     help_text='Name of recipient to make IBAN payouts to')
    autopayoutiban = forms.CharField(required=False, max_length=64, label='Recipient IBAN',
                                     help_text='IBAN number of account to make payouts to')
    notification_receiver = forms.EmailField(required=True)
    send_statements = forms.BooleanField(required=False, label="Send statements",
                                         help_text="Send monthly PDF statements by email")
    accounting_payout = forms.ChoiceField(required=False, choices=[(None, '---')] + get_account_choices(),
                                          label="Payout account")
    webhookurl = forms.CharField(label="Webhook URL", widget=StaticTextWidget)

    exclude_fields_from_validation = ('generatekey', )
    config_readonly = ['webhookurl', ]
    managed_fields = ['apikey', 'canrefund', 'notification_receiver', 'autopayout', 'autopayouttrigger',
                      'autopayoutlimit', 'autopayoutname', 'autopayoutiban', 'accounting_payout',
                      'send_statements', 'public_key', 'private_key', 'generatekey', ]
    managed_fieldsets = [
        {
            'id': 'tw',
            'legend': 'TransferWise',
            'fields': ['notification_receiver', 'send_statements', 'canrefund', 'apikey', 'generatekey', 'public_key', 'private_key'],
        },
        {
            'id': 'twautopayout',
            'legend': 'Automatic Payouts',
            'fields': ['autopayout', 'autopayouttrigger', 'autopayoutlimit',
                       'autopayoutname', 'autopayoutiban', 'accounting_payout'],
        },
        {
            'id': 'twconf',
            'legend': 'TransferWise configuration',
            'fields': ['webhookurl', ],
        },
    ]

    def fix_fields(self):
        super().fix_fields()
        self.fields['generatekey'].callback = self.generate_keypair
        self.initial['webhookurl'] = """
On the TransferWise account, go into <i>Settings</i> and click
<i>Create new webhook</i>. Give it a reasonable name, set it to
receive <i>Balance deposit events</i>, and specify the URL
<code>{}/wh/tw/{}/balance/</code>.""".format(
            settings.SITEBASE,
            self.instance.id,
        )

    def generate_keypair(self, request):
        (private, public) = generate_rsa_keypair()
        self.instance.config['public_key'] = public
        self.instance.config['private_key'] = private
        self.instance.save(update_fields=['config'])

        messages.info(request, "New RSA keypair generated")
        return True

    def clean(self):
        cleaned_data = super(BackendTransferwiseForm, self).clean()
        if cleaned_data['autopayout']:
            if not cleaned_data.get('canrefund', None):
                self.add_error('autopayout', 'Automatic payouts can only be enabled if refunds are enabled')

            # If auto payouts are enabled, a number of fields become mandateory
            for fn in ('autopayouttrigger', 'autopayoutlimit', 'autopayoutname', 'autopayoutiban', 'accounting_payout'):
                if not cleaned_data.get(fn, None):
                    self.add_error(fn, 'This field is required when automatic payouts are enabled')

            if cleaned_data['autopayoutlimit'] >= cleaned_data['autopayouttrigger']:
                self.add_error('autopayoutlimit', 'This value must be lower than the trigger value')

            # Actually make an API call to validate the IBAN
            if 'autopayoutiban' in cleaned_data and cleaned_data['autopayoutiban']:
                pm = self.instance.get_implementation()
                api = pm.get_api()
                try:
                    if not api.validate_iban(cleaned_data['autopayoutiban']):
                        self.add_error('autopayoutiban', 'IBAN number could not be validated')
                except Exception as e:
                    self.add_error('autopayoutiban', 'IBAN number could not be validated: {}'.format(e))

        return cleaned_data

    @classmethod
    def validate_data_for(self, instance):
        pm = instance.get_implementation()
        api = pm.get_api()
        try:
            account = api.get_account()
            return """Successfully retreived information:

<pre>{0}</pre>
""".format(self.prettyprint_address(account['balances'][0]['bankDetails']))
        except Exception as e:
            return "Verification failed: {}".format(e)

    @classmethod
    def prettyprint_address(self, a, indent=''):
        s = StringIO()
        for k, v in a.items():
            if k == 'id':
                continue

            s.write(indent)
            if isinstance(v, dict):
                s.write(k)
                s.write(":\n")
                s.write(self.prettyprint_address(v, indent + '  '))
            else:
                s.write("{0:20s}{1}\n".format(k + ':', v))
        return s.getvalue()


class Transferwise(BaseManagedBankPayment):
    backend_form_class = BackendTransferwiseForm
    description = """
Pay using a direct IBAN bank transfer in {}. We
<strong>strongly advise</strong> not using this method if
making a payment from an account in a different currency,
as amounts must be exact and all fees covered by sender.
""".format(settings.CURRENCY_ABBREV)

    def render_page(self, request, invoice):
        return render(request, 'invoices/genericbankpayment.html', {
            'invoice': invoice,
            'bankinfo': self.config('bankinfo'),
        })

    def get_api(self):
        return TransferwiseApi(self)

    def _find_invoice_transaction(self, invoice):
        r = re.compile(r'Bank transfer from method {} with id (\d+)'.format(self.method.id))
        m = r.match(invoice.paymentdetails)
        if m:
            try:
                return (TransferwiseTransaction.objects.get(pk=m.groups(1)[0], paymentmethod=self.method), None)
            except TransferwiseTransaction.DoesNotExist:
                return (None, "not found")
        else:
            return (None, "unknown format")

    def can_autorefund(self, invoice):
        if not self.config('canrefund'):
            return False

        (trans, reason) = self._find_invoice_transaction(invoice)
        if trans:
            if not trans.counterpart_valid_iban:
                # If there is no valid IBAN on the counterpart, we won't be able to
                # refund this invoice.
                return False
            return True

        return False

    def autorefund(self, refund):
        if not self.config('canrefund'):
            raise Exception("Cannot process automatic refunds. Configuration has changed?")

        (trans, reason) = self._find_invoice_transaction(refund.invoice)
        if not trans:
            raise Exception(reason)

        api = self.get_api()
        refund.payment_reference = api.refund_transaction(
            trans,
            refund.id,
            refund.fullamount,
            '{0} refund {1}'.format(settings.ORG_SHORTNAME, refund.id),
        )

        # At this point, we succeeded. Anything that failed will bubble
        # up as an exception.
        return True

    def return_payment(self, trans):
        # Return a payment that is *not* attached to an invoice
        if not self.config('canrefund'):
            raise Exception("Cannot process automatic refunds. Configuration has changed?")

        twtrans = TransferwiseTransaction.objects.get(
            paymentmethod=trans.method,
            id=trans.methodidentifier,
        )

        payout = TransferwisePayout(
            paymentmethod=trans.method,
            amount=twtrans.amount,
            reference='{0} returned payment {1}'.format(settings.ORG_SHORTNAME, twtrans.id),
            counterpart_name=twtrans.counterpart_name,
            counterpart_account=twtrans.counterpart_account,
            uuid=uuid.uuid4(),
        )
        payout.save()
