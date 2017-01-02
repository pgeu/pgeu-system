from django import forms
from django.forms import ValidationError
from django.forms import widgets
from django.contrib.auth.models import User

from selectable.forms.widgets import AutoCompleteSelectWidget
from postgresqleu.accountinfo.lookups import UserLookup

from models import Invoice, InvoiceRow, InvoicePaymentMethod
from postgresqleu.accounting.models import Account, Object

class InvoiceForm(forms.ModelForm):
	hidden_until_finalized = ('total_amount', 'total_vat', 'remindersent', )
	available_in_finalized = ('recipient_user', 'recipient_email', 'allowedmethods',)
	accounting_account = forms.ChoiceField(choices=[], required=False)
	accounting_object = forms.ChoiceField(choices=[], required=False)

	def __init__(self, *args, **kwargs):
		super(InvoiceForm, self).__init__(*args, **kwargs)
		# Some fields are hidden until the invoice is final
		if not self.instance.finalized:
			for fld in self.hidden_until_finalized:
				del self.fields[fld]

		self.fields['invoicedate'].widget = widgets.DateInput()
		self.fields['duedate'].widget = widgets.DateInput()
		self.fields['canceltime'].widget = widgets.DateTimeInput()
		self.fields['allowedmethods'].widget = forms.CheckboxSelectMultiple()
		self.fields['allowedmethods'].queryset = InvoicePaymentMethod.objects.filter(active=True)
		self.fields['allowedmethods'].label_from_instance = lambda m: "{0} ({1})".format(m.name, m.internaldescription)

		self.fields['accounting_account'].choices = [(0, '----'),] + [(a.num, "%s: %s" % (a.num, a.name)) for a in Account.objects.filter(availableforinvoicing=True)]
		self.fields['accounting_object'].choices = [('', '----'),] + [(o.name, o.name) for o in Object.objects.filter(active=True)]

		if self.instance.finalized:
			# All fields should be read-only for finalized invoices
			for fn,f in self.fields.items():
				if self.instance.ispaid or not fn in self.available_in_finalized:
					if type(f.widget).__name__ in ('TextInput', 'Textarea', 'DateInput', 'DateTimeInput'):
						f.widget.attrs['readonly'] = "readonly"
					else:
						f.widget.attrs['disabled'] = True

	class Meta:
		model = Invoice
		exclude = ['finalized', 'pdf_invoice', 'pdf_receipt', 'paidat', 'paymentdetails', 'paidusing', 'processor', 'processorid', 'deleted', 'deletion_reason', 'refund', 'recipient_secret']
		widgets = {
			'recipient_user': AutoCompleteSelectWidget(lookup_class=UserLookup),
		}

	def clean(self):
		if not self.cleaned_data['recipient_user'] and self.cleaned_data.has_key('recipient_email') and self.cleaned_data['recipient_email']:
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
	amount = forms.IntegerField(required=True)
	reason = forms.CharField(max_length=100, required=True)
	confirm = forms.BooleanField()

	def __init__(self, invoice, *args, **kwargs):
		super(RefundForm, self).__init__(*args, **kwargs)
		self.invoice = invoice

		if self.data and self.data.has_key('amount') and self.data.has_key('reason'):
			if invoice.can_autorefund:
				self.fields['confirm'].help_text = "Check this box to confirm that you want to generate an <b>automatic</b> refund of this invoice."
			else:
				self.fields['confirm'].help_text = "check this box to confirm that you have <b>already</b> manually refunded this invoice."
		else:
			del self.fields['confirm']

	def clean_amount(self):
		errstr = "Amount must be an integer between 1 and {0}".format(self.invoice.total_amount)

		try:
			amount = int(self.cleaned_data['amount'])
			if amount < 1 or amount > self.invoice.total_amount:
				raise ValidatonError(errstr)
			return self.cleaned_data['amount']
		except:
			raise ValidationError(errstr)
