from django import forms
from django.core.validators import MinValueValidator, MaxValueValidator
from django.forms import ValidationError
from django.forms import widgets
from django.contrib.auth.models import User
from django.conf import settings

from decimal import Decimal

from postgresqleu.accountinfo.lookups import UserLookup
from postgresqleu.util.widgets import HtmlDateInput

from .models import Invoice, InvoiceRow, InvoicePaymentMethod
from postgresqleu.accounting.models import Account, Object
from postgresqleu.invoices.models import VatRate


class InvoiceForm(forms.ModelForm):
    hidden_until_finalized = ('total_amount', 'total_vat', 'remindersent', )
    available_in_finalized = ('recipient_user', 'recipient_email', 'allowedmethods', 'extra_bcc_list', )
    selectize_multiple_fields = ['recipient_user', ]

    accounting_account = forms.ChoiceField(choices=[], required=False)
    accounting_object = forms.ChoiceField(choices=[], required=False)

    def __init__(self, *args, **kwargs):
        super(InvoiceForm, self).__init__(*args, **kwargs)
        # Some fields are hidden until the invoice is final
        if not self.instance.finalized:
            for fld in self.hidden_until_finalized:
                del self.fields[fld]

        if not settings.EU_VAT:
            del self.fields['reverse_vat']

        if 'data' in kwargs and 'recipient_user' in kwargs['data'] and kwargs['data']['recipient_user'] != '':
            # Postback with this field, so allow this specifi cuser
            self.fields['recipient_user'].queryset = User.objects.filter(pk=kwargs['data']['recipient_user'])
        elif self.instance and self.instance.recipient_user:
            self.fields['recipient_user'].queryset = User.objects.filter(pk=self.instance.recipient_user.pk)
        else:
            self.fields['recipient_user'].queryset = User.objects.filter(pk=-1)

        self.fields['recipient_user'].label_from_instance = lambda u: '{0} {1} ({2})'.format(u.first_name, u.last_name, u.username)
        self.fields['canceltime'].widget = widgets.DateTimeInput()
        self.fields['allowedmethods'].widget = forms.CheckboxSelectMultiple()
        self.fields['allowedmethods'].queryset = InvoicePaymentMethod.objects.filter()
        self.fields['allowedmethods'].label_from_instance = lambda x: "{0}{1}".format(x.internaldescription, x.active and " " or " (INACTIVE)")

        self.fields['accounting_account'].choices = [(0, '----'), ] + [(a.num, "%s: %s" % (a.num, a.name)) for a in Account.objects.filter(availableforinvoicing=True)]
        self.fields['accounting_object'].choices = [('', '----'), ] + [(o.name, o.name) for o in Object.objects.filter(active=True)]

        if self.instance.finalized:
            # All fields should be read-only for finalized invoices
            for fn, f in list(self.fields.items()):
                if self.instance.ispaid or fn not in self.available_in_finalized:
                    f.required = False
                    if type(f.widget).__name__ in ('TextInput', 'Textarea', 'DateInput', 'DateTimeInput'):
                        f.widget.attrs['readonly'] = "readonly"
                    else:
                        f.widget.attrs['disabled'] = True

    class Meta:
        model = Invoice
        exclude = ['finalized', 'pdf_invoice', 'pdf_receipt', 'paidat', 'paymentdetails', 'paidusing', 'processor', 'processorid', 'deleted', 'deletion_reason', 'refund', 'recipient_secret']
        widgets = {
            # Can't use HtmlDateInput since that truncates to just date
            #            'invoicedate': HtmlDateInput(),
            'duedate': HtmlDateInput(),
        }

    def clean(self):
        if not self.cleaned_data['recipient_user'] and self.cleaned_data.get('recipient_email', None):
            # User not specified. If we can find one by email, auto-populate
            # the field.
            matches = User.objects.filter(email=self.cleaned_data['recipient_email'])
            if len(matches) == 1:
                self.cleaned_data['recipient_user'] = matches[0]

        if self.cleaned_data['accounting_account'] == "0":
            # Can't figure out how to store NULL automatically, so overwrite
            # it when we've seen the magic value of zero.
            self.cleaned_data['accounting_account'] = None
        return self.cleaned_data


class InvoiceRowForm(forms.ModelForm):
    class Meta:
        model = InvoiceRow
        exclude = []

    def __init__(self, *args, **kwargs):
        super(InvoiceRowForm, self).__init__(*args, **kwargs)
        self.fields['rowcount'].widget.attrs['class'] = "sumfield"
        self.fields['rowamount'].widget.attrs['class'] = "sumfield"
        self.fields['vatrate'].widget.attrs['class'] = "sumfield"
        self.fields['vatrate'].required = False

    def clean_rowamount(self):
        if self.cleaned_data['rowamount'] == 0:
            raise ValidationError("Must specify an amount!")
        return self.cleaned_data['rowamount']

    def clean_rowcount(self):
        if self.cleaned_data['rowcount'] <= 0:
            raise ValidationError("Must specify a count!")
        return self.cleaned_data['rowcount']


class RefundForm(forms.Form):
    amount = forms.DecimalField(required=True, label="Amount ex VAT", validators=[MinValueValidator(1), ])
    vatrate = forms.ModelChoiceField(queryset=VatRate.objects.all(), required=False)
    reason = forms.CharField(max_length=100, required=True, help_text="Note! Included in communication to invoice recipient!")
    confirm = forms.BooleanField()

    def __init__(self, invoice, *args, **kwargs):
        super(RefundForm, self).__init__(*args, **kwargs)
        self.invoice = invoice

        self.fields['amount'].validators.append(MaxValueValidator(invoice.total_refunds['remaining']['amount']))

        if self.data and 'amount' in self.data and 'reason' in self.data:
            if invoice.can_autorefund:
                self.fields['confirm'].help_text = "Check this box to confirm that you want to generate an <b>automatic</b> refund of this invoice."
            else:
                self.fields['confirm'].help_text = "check this box to confirm that you have <b>already</b> manually refunded this invoice."
        else:
            del self.fields['confirm']
