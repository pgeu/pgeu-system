from django.contrib import admin
from django import forms
from django.forms import ValidationError

from selectable.forms.widgets import AutoCompleteSelectWidget
from postgresqleu.accountinfo.lookups import UserLookup
from postgresqleu.util.admin import SelectableWidgetAdminFormMixin
from postgresqleu.util.forms import ConcurrentProtectedModelForm

from models import Invoice, InvoiceLog, InvoiceProcessor, InvoicePaymentMethod
from models import InvoiceRefund, VatRate

class InvoiceAdminForm(SelectableWidgetAdminFormMixin, ConcurrentProtectedModelForm):
	class Meta:
		model = Invoice
		exclude = []
		widgets = {
			'recipient_user': AutoCompleteSelectWidget(lookup_class=UserLookup),
		}

	def clean_recipient_email(self):
		if self.cleaned_data.has_key('finalized'):
			raise ValidationError("Can't edit email field on a finalized invoice!")
		return self.cleaned_data['recipient_email']
	def clean_recipient_name(self):
		if self.cleaned_data.has_key('finalized'):
			raise ValidationError("Can't edit name field on a finalized invoice!")
		return self.cleaned_data['recipient_name']
	def clean_recipient_address(self):
		if self.cleaned_data.has_key('finalized'):
			raise ValidationError("Can't edit address field on a finalized invoice!")
		return self.cleaned_data['recipient_address']
	def clean_title(self):
		if self.cleaned_data.has_key('finalized'):
			raise ValidationError("Can't edit title field on a finalized invoice!")
		return self.cleaned_data['title']
	def clean_total_amount(self):
		if self.cleaned_data.has_key('finalized'):
			raise ValidationError("Can't edit total amount field on a finalized invoice!")
		return self.cleaned_data['total_amount']
	def clean_total_vat(self):
		if self.cleaned_data.has_key('finalized'):
			raise ValidationError("Can't edit total vat field on a finalized invoice!")
		return self.cleaned_data['total_vat']
	def clean_processor(self):
		if "processor" in self.changed_data:
			raise ValidationError("Sorry, we never allow editing of the processor!")
		return self.cleaned_data['processor']

class InvoiceAdmin(admin.ModelAdmin):
	list_display = ('id', 'title', 'recipient_name', 'total_amount', 'ispaid')
	form = InvoiceAdminForm
	exclude = ['pdf_invoice', 'pdf_receipt', ]
	filter_horizontal = ['allowedmethods', ]
	readonly_fields = ['refund', ]

class InvoiceLogAdmin(admin.ModelAdmin):
	list_display = ('timestamp', 'message_trunc', 'sent',)

class InvoiceRefundAdmin(admin.ModelAdmin):
	list_display = ('registered', 'issued', 'completed', 'amount', 'vatamount', 'reason')

class InvoicePaymentMethodAdmin(admin.ModelAdmin):
	list_display = ('name', 'internaldescription', 'classname', )

admin.site.register(Invoice, InvoiceAdmin)
admin.site.register(InvoiceProcessor)
admin.site.register(InvoicePaymentMethod, InvoicePaymentMethodAdmin)
admin.site.register(InvoiceLog, InvoiceLogAdmin)
admin.site.register(InvoiceRefund, InvoiceRefundAdmin)
admin.site.register(VatRate)
