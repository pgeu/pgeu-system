from models import *
from django.conf import settings
from django.template import Context
from django.template.loader import get_template

from datetime import datetime
import os
import base64
import re
from Crypto.Hash import SHA256
from Crypto import Random

from postgresqleu.util.misc.invoice import PDFInvoice
from postgresqleu.mailqueue.util import send_simple_mail

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
							  'Receipt for PGEU invoice #%s' % self.invoice.id,
							  'pgeu_receipt_%s.pdf' % self.invoice.id,
							  self.invoice.pdf_receipt)
		InvoiceHistory(invoice=self.invoice, txt='Sent receipt').save()

	def email_invoice(self):
		if not self.invoice.pdf_invoice:
			return

		self._email_something('invoice.txt',
							  'PGEU invoice #%s' % self.invoice.id,
							  'pgeu_invoice_%s.pdf' % self.invoice.id,
							  self.invoice.pdf_invoice)
		InvoiceHistory(invoice=self.invoice, txt='Sent invoice').save()

	def email_reminder(self):
		if not self.invoice.pdf_invoice:
			return

		self._email_something('invoice_reminder.txt',
							  'PGEU invoice #%s - reminder' % self.invoice.id,
							  'pgeu_invoice_%s.pdf' % self.invoice.id,
							  self.invoice.pdf_invoice)
		InvoiceHistory(invoice=self.invoice, txt='Sent reminder').save()

	def email_cancellation(self):
		self._email_something('invoice_cancel.txt',
							  'PGEU invoice #%s - reminder' % self.invoice.id)
		InvoiceHistory(invoice=self.invoice, txt='Sent cancellation').save()

	def _email_something(self, template_name, mail_subject, pdfname=None, pdfcontents=None):
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
	def process_incoming_payment(self, transtext, transamount, transdetails, logger=None):
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
		# Returns a tuple of (status,invoice,processor)
		#
		m = re.match('^PostgreSQL Europe Invoice #(\d+) .*', transtext)
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

		return self.process_incoming_payment_for_invoice(invoice, transamount, transdetails, logger)


	def process_incoming_payment_for_invoice(self, invoice, transamount, transdetails, logger):
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

		# Send the receipt to the user if possible - that should make
		# them happy :)
		wrapper.email_receipt()

		# Write a log, because it's always nice..
		InvoiceHistory(invoice=invoice, txt='Processed payment').save()
		InvoiceLog(message="Processed payment of %s EUR for invoice %s (%s)" % (
				invoice.total_amount,
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
					   bankinfo = True):
		invoice = Invoice(
			recipient_email=recipient_email,
			recipient_name=recipient_name,
			recipient_address=recipient_address,
			title=title,
			invoicedate=invoicedate,
			duedate=duedate,
			total_amount=-1,
			bankinfo=bankinfo)
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

	def get_return_url(self, invoice):
		print "Trying to get the return url, but I can't!"
		return "http://unknown.postgresql.eu/"
