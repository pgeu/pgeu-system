from django.db import models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import User
from django.conf import settings

from datetime import datetime, timedelta
from decimal import Decimal

from payment import PaymentMethodWrapper

from postgresqleu.accounting.models import Account

class InvoiceProcessor(models.Model):
	# The processor name is purely cosmetic
	processorname = models.CharField(max_length=50, null=False, blank=False, unique=True)
	# Python class name (full path) to the class that should be
	# notified when an invoice has been processed.
	classname = models.CharField(max_length=200, null=False, blank=False)

	def __unicode__(self):
		return self.processorname

class InvoicePaymentMethod(models.Model):
	name = models.CharField(max_length=100, null=False, blank=False)
	active = models.BooleanField(null=False, blank=False, default=True)
	sortkey = models.IntegerField(null=False, blank=False, default=100)
	internaldescription = models.CharField(max_length=100, null=False, blank=True)
	# Python class name (full path) to the class that implements
	# this payment method.
	classname = models.CharField(max_length=200, null=False, blank=False, unique=True)
	auto = models.BooleanField(null=False, blank=False, default=True, verbose_name="Used by automatically generated invoices")

	def __unicode__(self):
		return self.name

	class Meta:
		ordering = ['sortkey',]

class InvoiceRefund(models.Model):
	reason = models.CharField(max_length=500, null=False, blank=True, default='', help_text="Reason for refunding of invoice")

	amount = models.DecimalField(max_digits=10, decimal_places=2, null=False)
	vatamount = models.DecimalField(max_digits=10, decimal_places=2, null=False)
	vatrate = models.ForeignKey('VatRate', null=True)

	registered = models.DateTimeField(null=False, auto_now_add=True)
	issued = models.DateTimeField(null=True, blank=True)
	completed = models.DateTimeField(null=True, blank=True)

	payment_reference = models.CharField(max_length=100, null=False, blank=True, help_text="Reference in payment system, depending on system used for invoice.")

	refund_pdf = models.TextField(blank=True, null=False)

	@property
	def fullamount(self):
		return self.amount + self.vatamount

class Invoice(models.Model):
	# pk = invoice number, which is fully exposed.

	# The recipient. We set the user if we have matched it to a
	# community account, but support invoices that are just listed
	# by name. If email is set, we can retro-match it up, but once
	# a recipient is matched, the recipient_user field "owns" the
	# recipient information.
	recipient_user = models.ForeignKey(User, null=True, blank=True)
	recipient_email = models.EmailField(blank=True, null=False)
	recipient_name = models.CharField(max_length=100, blank=False, null=False)
	recipient_address = models.TextField(blank=False, null=False)
	recipient_secret = models.CharField(max_length=64, blank=True, null=True)

	# Global invoice info
	title = models.CharField(max_length=100, blank=False, null=False, verbose_name="Invoice title")
	invoicedate = models.DateTimeField(null=False, blank=False)
	duedate = models.DateTimeField(null=False, blank=False)
	canceltime = models.DateTimeField(null=True, blank=True, help_text="Invoice will automatically be canceled at this time")

	# Amount information is calculated when the invoice is finalized
	total_amount = models.DecimalField(decimal_places=2, max_digits=10, null=False)
	total_vat = models.DecimalField(decimal_places=2, max_digits=10, null=False, default=0)
	finalized = models.BooleanField(null=False, blank=True, default=False, help_text="Invoice is finalized, should not ever be changed again")
	deleted = models.BooleanField(null=False, blank=False, default=False, help_text="This invoice has been deleted")
	deletion_reason = models.CharField(max_length=500, null=False, blank=True, default='', help_text="Reason for deletion of invoice")

	refund = models.OneToOneField(InvoiceRefund, null=True, blank=True, on_delete=models.SET_NULL)

	# base64 encoded version of the PDF invoice
	pdf_invoice = models.TextField(blank=True, null=False)

	# Which class, if any, is responsible for processing the payment
	# of this invoice. This can typically be to flag a conference
	# payment as done once the payment is in. processorid is an arbitrary
	# id value that the processor can use for whatever it wants.
	processor = models.ForeignKey(InvoiceProcessor, null=True, blank=True)
	processorid = models.IntegerField(null=True, blank=True)

	# Allowed payment methods
	allowedmethods = models.ManyToManyField(InvoicePaymentMethod, null=False, blank=True, verbose_name="Allowed payment methods")
	bankinfo = models.BooleanField(null=False, blank=False, default=True, verbose_name="Include bank details on invoice")

	# Payment status of this invoice. Once it's paid, the payment system
	# writes the details of the transaction to the paymentdetails field.
	paidat = models.DateTimeField(null=True, blank=True)
	paymentdetails = models.CharField(max_length=100, null=False, blank=True)
	paidusing = models.ForeignKey(InvoicePaymentMethod, null=True, blank=True, related_name="paidusing", verbose_name="Payment method actually used")

	# Reminder (if any) sent when?
	remindersent = models.DateTimeField(null=True, blank=True, verbose_name="Automatic reminder sent at")

	# Once an invoice is paid, a recipient is generated. PDF base64
	pdf_receipt = models.TextField(blank=True, null=False)

	# Information for accounting of this invoice. This is intentionally not
	# foreign keys - we'll just drop some such information into the system
	# manually in the forms.
	accounting_account = models.IntegerField(null=True, blank=True, verbose_name="Accounting account")
	accounting_object = models.CharField(null=True, blank=True, max_length=30, verbose_name="Accounting object")

	@property
	def has_recipient_user(self):
		return self.recipientuser and True or False

	@property
	def ispaid(self):
		return self.paidat is not None

	@property
	def isexpired(self):
		return (self.paidat is None) and (self.duedate < datetime.now())

	@property
	def allowedmethodwrappers(self):
		return [PaymentMethodWrapper(m, self) for m in self.allowedmethods.all()]

	@property
	def invoicestr(self):
		return "%s #%s - %s" % (settings.INVOICE_TITLE_PREFIX, self.pk, self.title)

	@property
	def payment_fees(self):
		if self.paidusing:
			return PaymentMethodWrapper(self.paidusing, self).payment_fees
		else:
			return "unknown"

	@property
	def amount_without_fees(self):
		f = self.payment_fees
		if type(f) == str:
			return "Unknown"
		else:
			return self.total_amount - f

	@property
	def can_autorefund(self):
		return PaymentMethodWrapper(self.paidusing, self).can_autorefund

	def autorefund(self):
		return PaymentMethodWrapper(self.paidusing, self).autorefund()

	def __unicode__(self):
		return "Invoice #%s" % self.pk

	class Meta:
		ordering = ('-id', )


class VatRate(models.Model):
	name = models.CharField(max_length=100, blank=False, null=False)
	shortname = models.CharField(max_length=16, blank=False, null=False)
	vatpercent = models.IntegerField(null=False, default=0, verbose_name="VAT percentage",
									 validators=[MaxValueValidator(100), MinValueValidator(0)])
	vataccount = models.ForeignKey(Account, null=False, blank=False)

	_safe_attributes = ('vatpercent', 'shortstr', 'shortname', 'name')

	def __unicode__(self):
		return u"{0} ({1}%)".format(self.name, self.vatpercent)

	@property
	def shortstr(self):
		return "%s%% (%s)" % (self.vatpercent, self.shortname)

class InvoiceRow(models.Model):
	# Invoice rows are only used up until the invoice is finished,
	# but allows us to save a half-finished invoice.
	invoice = models.ForeignKey(Invoice, null=False)
	rowtext = models.CharField(max_length=100, blank=False, null=False, verbose_name="Text")
	rowcount = models.IntegerField(null=False, default=1, verbose_name="Count")
	rowamount = models.DecimalField(decimal_places=2, max_digits=10, null=False, default=0, verbose_name="Amount per item (ex VAT)")
	vatrate = models.ForeignKey(VatRate, null=True)

	def __unicode__(self):
		return self.rowtext

	def __unicode__(self):
		return self.rowtext

	@property
	def totalvat(self):
		if self.vatrate:
			return self.rowamount * self.rowcount * self.vatrate.vatpercent / Decimal(100)
		else:
			return 0

	@property
	def totalrow(self):
		return self.rowamount * self.rowcount

	@property
	def totalwithvat(self):
		return self.totalrow + self.totalvat

class InvoiceHistory(models.Model):
	invoice = models.ForeignKey(Invoice, null=False)
	time = models.DateTimeField(null=False, blank=False, auto_now_add=True)
	txt = models.CharField(max_length=100, null=False, blank=False)

	class Meta:
		ordering = ['time',]

	def __unicode__(self):
		return self.txt

class InvoiceLog(models.Model):
	timestamp = models.DateTimeField(null=False, blank=False, auto_now_add=True)
	message = models.TextField(null=False, blank=False)
	sent = models.BooleanField(null=False, blank=False, default=False)

	@property
	def message_trunc(self):
		return self.message[:150]

	class Meta:
		ordering = ['-timestamp', ]
