from models import Invoice, InvoiceRow, InvoiceHistory, InvoiceLog
from models import InvoicePaymentMethod, PaymentMethodWrapper
from django.conf import settings
from django.template import Context
from django.template.loader import get_template

from datetime import datetime, date
import importlib
import os
import base64
import re
from Crypto.Hash import SHA256
from Crypto import Random

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.accounting.util import create_accounting_entry

# Proxy around an invoice that adds presentation information,
# such as the ability to render a return URL for the invoice.
class InvoicePresentationWrapper(Invoice):
	def __init__(self, invoice, returnurl):
		self.__invoice = invoice
		self.__returnurl = returnurl
	def __getattr__(self, name):
		return getattr(self.__invoice, name)

	@property
	def allowedmethodwrappers(self):
		return [PaymentMethodWrapper(m, self.invoicestr, self.total_amount, self.pk, self.__returnurl) for m in self.allowedmethods.all()]


# Functionality wrapper around an invoice that allows actions
# to be performed on it, such as creating PDFs.
class InvoiceWrapper(object):
	def __init__(self, invoice):
		self.invoice = invoice

	def finalizeInvoice(self):
		# This will close out this invoice for editing, and also
		# generate the actual PDF

		# Calculate the total
		total = 0
		for r in self.invoice.invoicerow_set.all():
			total += r.rowamount * r.rowcount
		self.invoice.total_amount = total

		# Generate pdf
		self.invoice.pdf_invoice = base64.b64encode(self.render_pdf_invoice())

		# Indicate that we're finalized
		self.invoice.finalized = True

		# Generate a secret key that can be used to view the invoice if
		# there is no associated account
		s = SHA256.new()
		r = Random.new()
		s.update(self.invoice.pdf_invoice)
		s.update(r.read(250))
		self.invoice.recipient_secret = s.hexdigest()

		# And we're done!
		self.invoice.save()
		InvoiceHistory(invoice=self.invoice, txt='Finalized').save()

	def render_pdf_invoice(self, preview=False):
		return self._render_pdf(preview=preview, receipt=False)

	def render_pdf_receipt(self):
		return self._render_pdf(receipt=True)

	def _render_pdf(self, preview=False, receipt=False):
		PDFInvoice = getattr(importlib.import_module(settings.INVOICE_PDF_BUILDER), 'PDFInvoice')
		pdfinvoice = PDFInvoice("%s\n%s" % (self.invoice.recipient_name, self.invoice.recipient_address),
								self.invoice.invoicedate,
								receipt and self.invoice.paidat or self.invoice.duedate,
								self.invoice.pk,
								os.path.realpath('%s/../../media/img/' % os.path.dirname(__file__)),
								preview=preview,
								receipt=receipt,
								bankinfo=self.invoice.bankinfo)

		for r in self.invoice.invoicerow_set.all():
			pdfinvoice.addrow(r.rowtext, r.rowamount, r.rowcount)

		return pdfinvoice.save().getvalue()

	def email_receipt(self):
		# If no receipt exists yet, we have to bail too
		if not self.invoice.pdf_receipt:
			return

		self._email_something('paid_receipt.txt',
							  'Receipt for %s #%s' % (settings.INVOICE_TITLE_PREFIX, self.invoice.id),
							  '%s_receipt_%s.pdf' % (settings.INVOICE_FILENAME_PREFIX, self.invoice.id),
							  self.invoice.pdf_receipt,
							  bcc=(self.invoice.processor is None))
		InvoiceHistory(invoice=self.invoice, txt='Sent receipt').save()

	def email_invoice(self):
		if not self.invoice.pdf_invoice:
			return

		self._email_something('invoice.txt',
							  '%s #%s' % (settings.INVOICE_TITLE_PREFIX, self.invoice.id),
							  '%s_invoice_%s.pdf' % (settings.INVOICE_FILENAME_PREFIX, self.invoice.id),
							  self.invoice.pdf_invoice,
							  bcc=True)
		InvoiceHistory(invoice=self.invoice, txt='Sent invoice').save()

	def email_reminder(self):
		if not self.invoice.pdf_invoice:
			return

		self._email_something('invoice_reminder.txt',
							  '%s #%s - reminder' % (settings.INVOICE_TITLE_PREFIX, self.invoice.id),
							  '%s_invoice_%s.pdf' % (settings.INVOICE_FILENAME_PREFIX, self.invoice.id),
							  self.invoice.pdf_invoice,
							  bcc=True)
		InvoiceHistory(invoice=self.invoice, txt='Sent reminder').save()

	def email_cancellation(self):
		self._email_something('invoice_cancel.txt',
							  '%s #%s - canceled' % (settings.INVOICE_TITLE_PREFIX, self.invoice.id),
							  bcc=True)
		InvoiceHistory(invoice=self.invoice, txt='Sent cancellation').save()

	def email_refund(self):
		self._email_something('invoice_refund.txt',
							  '%s #%s - refund notice' % (settings.INVOICE_TITLE_PREFIX, self.invoice.id),
							  bcc=True)
		InvoiceHistory(invoice=self.invoice, txt='Sent refund notice').save()

	def _email_something(self, template_name, mail_subject, pdfname=None, pdfcontents=None, bcc=False):
		# Send off the receipt/invoice by email if possible
		if not self.invoice.recipient_email:
			return

		# Build a text email, and attach the PDF if there is one
		if self.invoice.recipient_user:
			# General URL that shows a normal invoice
			invoiceurl = '%s/invoices/%s/' % (settings.SITEBASE_SSL, self.invoice.pk)
		elif self.invoice.recipient_secret:
			# No user, but a secret, so generate a URL that can be used without
			# being logged in.
			invoiceurl = '%s/invoices/%s/%s/' % (settings.SITEBASE_SSL, self.invoice.pk, self.invoice.recipient_secret)
		else:
			invoiceurl = None

		txt = get_template('invoices/mail/%s' % template_name).render(Context({
				'invoice': self.invoice,
				'invoiceurl': invoiceurl,
				'currency_abbrev': settings.CURRENCY_ABBREV,
				'currency_symbol': settings.CURRENCY_SYMBOL,
				}))

		pdfdata = []
		if pdfname:
			pdfdata = [(pdfname, 'application/pdf',	base64.b64decode(pdfcontents)), ]

		# Queue up in the database for email sending soon
		send_simple_mail(settings.INVOICE_SENDER_EMAIL,
						 self.invoice.recipient_email,
						 mail_subject,
						 txt,
						 pdfdata,
						 bcc=bcc and settings.INVOICE_SENDER_EMAIL or None,
						 )


def _standard_logger(message):
	print message

class InvoiceManager(object):
	def __init__(self):
		pass

	RESULT_OK = 0
	RESULT_NOTFOUND = 1
	RESULT_NOTSENT = 2
	RESULT_ALREADYPAID = 3
	RESULT_DELETED = 4
	RESULT_INVALIDAMOUNT = 5
	RESULT_PROCESSORFAIL = 6
	def process_incoming_payment(self, transtext, transamount, transdetails, transcost, incomeaccount, costaccount, extraurls=None, logger=None):
		# If there is no logger specified, just log with print statement
		if not logger:
			logger = _standard_logger

		# Look for a matching invoice, by transtext. We assume the
		# trantext is "PostgreSQL Europe Invoice #nnn - <whatever>"
		#
		# Transdetails are the ones written to the record as payment
		# details for permanent reference. This can be for example the
		# payment systems transaction id.
		#
		# Transcost is the cost of this transaction. If set to 0, no
		#           accounting row will be written for the cost.
		# Incomeaccount is the account number to debit the income to
		# Costaccount is the account number to credit the cost to
		#
		# The credit of the actual income is already noted on the,
		# invoice since it's not dependent on the payment method.
		#
		# Returns a tuple of (status,invoice,processor)
		#
		m = re.match('^%s #(\d+) .*' % settings.INVOICE_TITLE_PREFIX, transtext)
		if not m:
			logger("Could not match transaction text '%s'" % transtext)
			return (self.RESULT_NOTFOUND, None, None)

		try:
			invoiceid = int(m.groups(1)[0])
		except:
			logger("Could not match transaction id from '%s'" % transtext)
			return (self.RESULT_NOTFOUND, None, None)

		try:
			invoice = Invoice.objects.get(pk=invoiceid)
		except Invoice.DoesNotExist:
			logger("Could not find invoice with id '%s'" % invoiceid)
			return (self.RESULT_NOTFOUND, None, None)

		return self.process_incoming_payment_for_invoice(invoice, transamount, transdetails, transcost, incomeaccount, costaccount, extraurls, logger)


	def process_incoming_payment_for_invoice(self, invoice, transamount, transdetails, transcost, incomeaccount, costaccount, extraurls, logger):
		# Do the same as process_incoming_payment, but assume that the
		# invoice has already been matched by other means.
		invoiceid = invoice.pk

		if not invoice.finalized:
			logger("Invoice %s was never sent!" % invoiceid)
			return (self.RESULT_NOTSENT, None, None)

		if invoice.ispaid:
			logger("Invoice %s already paid!" % invoiceid)
			return (self.RESULT_ALREADYPAID, None, None)

		if invoice.deleted:
			logger("Invoice %s has been deleted!" % invoiceid)
			return (self.RESULT_DELETED, None, None)

		if invoice.total_amount != transamount:
			logger("Invoice %s, received payment of %s, expected %s!" % (invoiceid, transamount, invoice.total_amount))
			return (self.RESULT_INVALIDAMOUNT, None, None)

		# Things look good, flag this invoice as paid
		invoice.paidat = datetime.now()
		invoice.paymentdetails = transdetails

		# If there is a processor module registered for this invoice,
		# we need to instantiate it and call it. So, well, let's do
		# that.
		processor = None
		if invoice.processor:
			processor = self.get_invoice_processor(invoice, logger=logger)
			if not processor:
				# get_invoice_processor() has already logged
				return (self.RESULT_PROCESSORFAIL, None, None)
			try:
				processor.process_invoice_payment(invoice)
			except Exception, ex:
				logger("Failed to run invoice processor '%s': %s" % (invoice.processor, ex))
				return (self.RESULT_PROCESSORFAIL, None, None)

		# Generate a PDF receipt for this, since it's now paid
		wrapper = InvoiceWrapper(invoice)
		invoice.pdf_receipt = base64.b64encode(wrapper.render_pdf_receipt())

		# Save and we're done!
		invoice.save()

		# Create an accounting entry for this invoice. If we have the required
		# information on the invoice, we can finalize it. If not, we will
		# need to create an open ended one.
		accountingtxt = 'Invoice #%s: %s' % (invoice.id, invoice.title)
		accrows = [
			(incomeaccount, accountingtxt, invoice.total_amount-transcost, None),
			]
		if transcost > 0:
			# If there was a transaction cost known at this point (which
			# it typically is with Paypal), make sure we book a row for it.
			accrows.append(
			(costaccount, accountingtxt, transcost, invoice.accounting_object),
		)
		if invoice.accounting_account:
			accrows.append(
				(invoice.accounting_account, accountingtxt, -invoice.total_amount, invoice.accounting_object),
			)
			leaveopen = False
		else:
			leaveopen = True
		urls = ['%s/invoices/%s/' % (settings.SITEBASE_SSL, invoice.pk),]
		if extraurls:
			urls.extend(extraurls)

		create_accounting_entry(date.today(), accrows, leaveopen, urls)

		# Send the receipt to the user if possible - that should make
		# them happy :)
		wrapper.email_receipt()

		# Write a log, because it's always nice..
		InvoiceHistory(invoice=invoice, txt='Processed payment').save()
		InvoiceLog(message="Processed payment of %s %s for invoice %s (%s)" % (
				invoice.total_amount,
				settings.CURRENCY_ABBREV,
				invoice.pk,
				invoice.title),
				   timestamp=datetime.now()).save()

		return (self.RESULT_OK, invoice, processor)

	def get_invoice_processor(self, invoice, logger=None):
		if invoice.processor:
			try:
				pieces = invoice.processor.classname.split('.')
				modname = '.'.join(pieces[:-1])
				classname = pieces[-1]
				mod = __import__(modname, fromlist=[classname, ])
				return getattr(mod, classname) ()
			except Exception, ex:
				if logger:
					logger("Failed to instantiate invoice processor '%s': %s" % (invoice.processor, ex))
					return None
				else:
					raise Exception("Failed to instantiate invoice processor '%s': %s" % (invoice.processor, ex))
		else:
			return None

	# Cancel the specified invoice, calling any processor set on it if necessary
	def cancel_invoice(self, invoice, reason):
		# If this invoice has a processor, we need to start by calling it
		processor = self.get_invoice_processor(invoice)
		if processor:
			try:
				processor.process_invoice_cancellation(invoice)
			except Exception, ex:
				raise Exception("Failed to run invoice processor '%s': %s" % (invoice.processor, ex))

		invoice.deleted = True
		invoice.deletion_reason = reason
		invoice.save()

		InvoiceHistory(invoice=invoice, txt='Canceled').save()

		# Send the receipt to the user if possible - that should make
		# them happy :)
		wrapper = InvoiceWrapper(invoice)
		wrapper.email_cancellation()

		InvoiceLog(timestamp=datetime.now(), message="Deleted invoice %s: %s" % (invoice.id, invoice.deletion_reason)).save()

	def refund_invoice(self, invoice, reason):
		# If this invoice has a processor, we need to start by calling it
		processor = self.get_invoice_processor(invoice)
		if processor:
			try:
				processor.process_invoice_refund(invoice)
			except Exception, ex:
				raise Exception("Failed to run invoice processor '%s': %s" % (invoice.processor, ex))

		invoice.refunded = True
		invoice.refund_reason = reason
		invoice.save()

		InvoiceHistory(invoice=invoice, txt='Refunded').save()

		# Send the receipt to the user if possible - that should make
		# them happy :)
		wrapper = InvoiceWrapper(invoice)
		wrapper.email_refund()

		InvoiceLog(timestamp=datetime.now(), message="Refunded invoice %s: %s" % (invoice.id, invoice.deletion_reason)).save()

	# This creates a complete invoice, and finalizes it
	def create_invoice(self,
					   recipient_user,
					   recipient_email,
					   recipient_name,
					   recipient_address,
					   title,
					   invoicedate,
					   duedate,
					   invoicerows,
					   processor = None,
					   processorid = None,
					   autopaymentoptions = True,
					   bankinfo = True,
					   accounting_account = None,
					   accounting_object = None):
		invoice = Invoice(
			recipient_email=recipient_email,
			recipient_name=recipient_name,
			recipient_address=recipient_address,
			title=title,
			invoicedate=invoicedate,
			duedate=duedate,
			total_amount=-1,
			bankinfo=bankinfo,
			accounting_account=accounting_account,
			accounting_object=accounting_object)
		if recipient_user:
			invoice.recipient_user = recipient_user
		if processor:
			invoice.processor = processor
		if processorid:
			invoice.processorid = processorid
		# Add our rows. Need to save the invoice first so it has an id.
		# But we expect to be in a transaction anyway.
		invoice.save()
		for r in invoicerows:
			invoice.invoicerow_set.add(InvoiceRow(invoice=invoice,
												  rowtext = r[0],
												  rowcount = r[1],
												  rowamount = r[2]))

		if autopaymentoptions:
			invoice.allowedmethods = InvoicePaymentMethod.objects.filter(auto=True)
			invoice.save()

		# That should be it. Finalize so we get a PDF, and then
		# return whatever we have.
		wrapper = InvoiceWrapper(invoice)
		wrapper.finalizeInvoice()
		return invoice


# This is purely for testing, obviously
class TestProcessor(object):
	def process_invoice_payment(self, invoice):
		print "Callback processing invoice with title '%s', for my own id %s" % (invoice.title, invoice.processorid)
	def process_invoice_cancellation(self, invoice):
		raise Exception("This processor can't cancel invoices.")
	def process_invoice_refund(self, invoice):
		raise Exception("This processor can't refund invoices.")

	def get_return_url(self, invoice):
		print "Trying to get the return url, but I can't!"
		return "http://unknown.postgresql.eu/"
