from django import forms
from django.shortcuts import render
from django.conf import settings

import re
import uuid
from io import StringIO

from postgresqleu.util.payment.banktransfer import BaseManagedBankPayment
from postgresqleu.util.payment.banktransfer import BaseManagedBankPaymentForm
from postgresqleu.transferwise.api import TransferwiseApi

from postgresqleu.invoices.models import Invoice
from postgresqleu.transferwise.models import TransferwiseTransaction, TransferwisePayout


class BackendTransferwiseForm(BaseManagedBankPaymentForm):
    apikey = forms.CharField(required=True, widget=forms.widgets.PasswordInput(render_value=True))
    canrefund = forms.BooleanField(required=False, label='Can refund',
                                   help_text='Process automatic refunds. This requires an API key with full access to make transfers to any accounts')

    managed_fields = ['apikey', 'canrefund', ]
    managed_fieldsets = [
        {
            'id': 'tw',
            'legend': 'TransferWise',
            'fields': ['canrefund', 'apikey', ],
        }
    ]

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
Pay using a direct IBAN bank transfer in EUR. We
<strong>strongly advice</strong> not using this method if
making a payment from outside the Euro-zone, as amounts
must be exact and all fees covered by sender.
"""

    def render_page(self, request, invoice):
        return render(request, 'transferwise/payment.html', {
            'invoice': invoice,
            'bankinfo': self.config('bankinfo'),
        })

    def get_api(self):
        return TransferwiseApi(self)

    def _find_invoice_transaction(self, invoice):
        r = re.compile('Bank transfer from {} with id (\d+)'.format(self.method.internaldescription))
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
