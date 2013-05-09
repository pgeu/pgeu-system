from django.db import models
from django.contrib.auth.models import User

from datetime import datetime, timedelta
from payment import PaymentMethodWrapper

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
	# Python class name (full path) to the class that implements
	# this payment method.
	classname = models.CharField(max_length=200, null=False, blank=False)
	auto = models.BooleanField(null=False, blank=False, default=True, verbose_name="Used by automatically generated invoices")

	def __unicode__(self):
		return self.name

	class Meta:
		ordering = ['sortkey',]

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

	# Global invoice info
	title = models.CharField(max_length=100, blank=False, null=False, verbose_name="Invoice title")
	invoicedate = models.DateTimeField(null=False, blank=False, default=datetime.now)
	duedate = models.DateTimeField(null=False, blank=False, default=datetime.now()+timedelta(days=31))

	# Amount information is calculated when the invoice is finalized
	total_amount = models.IntegerField(null=False)
	finalized = models.BooleanField(null=False, blank=True, help_text="Invoice is finalized, should not ever be changed again")
	deleted = models.BooleanField(null=False, blank=False, default=False, help_text="This invoice has been deleted")

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

	# Once an invoice is paid, a recipient is generated. PDF base64
	pdf_receipt = models.TextField(blank=True, null=False)

	@property
	def ispaid(self):
		return self.paidat is not None

	@property
	def allowedmethodwrappers(self):
		return [PaymentMethodWrapper(m, self.invoicestr, self.total_amount, self.pk) for m in self.allowedmethods.all()]

	@property
	def invoicestr(self):
		return "PostgreSQL Europe Invoice #%s - %s" % (self.pk, self.title)

	def __unicode__(self):
		return "Invoice #%s" % self.pk

	class Meta:
		ordering = ('-id', )

class InvoiceRow(models.Model):
	# Invoice rows are only used up until the invoice is finished,
	# but allows us to save a half-finished invoice.
	invoice = models.ForeignKey(Invoice, null=False)
	rowtext = models.CharField(max_length=100, blank=False, null=False, verbose_name="Text")
	rowcount = models.IntegerField(null=False, default=1, verbose_name="Count")
	rowamount = models.IntegerField(null=False, default=0, verbose_name="Amount per item")

class InvoiceLog(models.Model):
	timestamp = models.DateTimeField(null=False, blank=False, default=datetime.now())
	message = models.TextField(null=False, blank=False)
	sent = models.BooleanField(null=False, blank=False, default=False)

	@property
	def message_trunc(self):
		return self.message[:150]

	class Meta:
		ordering = ['-timestamp', ]
