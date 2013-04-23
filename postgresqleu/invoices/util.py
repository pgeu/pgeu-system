from django.db import connection
from models import *
from django.conf import settings
from django.template import Context
from django.template.loader import get_template

from datetime import datetime
import os
import base64
import re

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

		# And we're done!
		self.invoice.save()

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
								receipt=receipt)

		for r in self.invoice.invoicerow_set.all():
			pdfinvoice.addrow(r.rowtext, r.rowamount, r.rowcount)

		return pdfinvoice.save().getvalue()

	def email_receipt(self):
		# Send off the receipt by email if possile
		if not self.invoice.recipient_email:
			return

		# If no receipt exists yet, we have to bail too
		if not self.invoice.pdf_receipt:
			return

		# Build a text email, and attach the PDF
		txt = get_template('invoices/mail/paid_receipt.txt').render(Context({
				'invoice': self.invoice,
				}))

		# Queue up in the database for email sending soon
		send_simple_mail(settings.INVOICE_SENDER_EMAIL,
						 self.invoice.recipient_email,
						 "Receipt for PGEU invoice #%s" % self.invoice.id,
						 txt,
						 [('pgeu_receipt_%s.pdf' % self.invoice.id,
						   'application/pdf',
						   self.invoice.pdf_receipt),
						  ],
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
		m = re.match('^PostgreSQL Europe Invoice #(\d+) .*', transtext)
		if not m:
			logger("Could not match transaction text '%s'" % transtext)
			return self.RESULT_NOTFOUND

		try:
			invoiceid = int(m.groups(1)[0])
		except:
			logger("Could not match transaction id from '%s'" % transtext)
			return self.RESULT_NOTFOUND

		try:
			invoice = Invoice.objects.get(pk=invoiceid)
		except Invoice.DoesNotExist:
			logger("Could not find invoice with id '%s'" % invoiceid)
			return self.RESULT_NOTFOUND

		if not invoice.finalized:
			logger("Invoice %s was never sent!" % invoiceid)
			return self.RESULT_NOTSENT

		if invoice.ispaid:
			logger("Invoice %s already paid!" % invoiceid)
			return self.RESULT_ALREADYPAID

		if invoice.deleted:
			logger("Invoice %s has been deleted!" % invoiceid)
			return self.RESULT_DELETED

		if invoice.total_amount != transamount:
			logger("Invoice %s, received payment of %s, expected %s!" % (invoiceid, transamount, invoice.total_amount))
			return self.RESULT_INVALIDAMOUNT

		# Things look good, flag this invoice as paid
		invoice.paidat = datetime.now()
		invoice.paymentdetails = transdetails

		# If there is a processor module registered for this invoice,
		# we need to instantiate it and call it. So, well, let's do
		# that.
		if invoice.processor:
			processor = None
			try:
				pieces = invoice.processor.classname.split('.')
				modname = '.'.join(pieces[:-1])
				classname = pieces[-1]
				mod = __import__(modname, fromlist=[classname, ])
				processor = getattr(mod, classname) ()
			except Exception, ex:
				logger("Failed to instantiate invoice processor '%s': %s" % (invoice.processor, ex))

			try:
				processor.process_invoice_payment(invoice)
			except Exception, ex:
				logger("Failed to run invoice processor '%s': %s" % (invoice.processor, ex))
				return self.RESULT_PROCESSORFAIL

		# Generate a PDF receipt for this, since it's now paid
		wrapper = InvoiceWrapper(invoice)
		invoice.pdf_receipt = base64.b64encode(wrapper.render_pdf_receipt())

		# Save and we're done!
		invoice.save()

		# Send the receipt to the user if possible - that should make
		# them happy :)
		wrapper.email_receipt()

		# Write a log, because it's always nice..
		InvoiceLog(message="Processed payment of %s EUR for invoice %s (%s)" % (
				invoice.total_amount,
				invoice.pk,
				invoice.title)).save()

		return self.RESULT_OK

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
					   autopaymentoptions = True):
		invoice = Invoice(
			recipient_email=recipient_email,
			recipient_name=recipient_name,
			recipient_address=recipient_address,
			title=title,
			invoicedate=invoicedate,
			duedate=duedate,
			total_amount=-1)
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

	def get_return_url(self, invoice):
		print "Trying to get the return url, but I can't!"
		return "http://unknown.postgresql.eu/"
