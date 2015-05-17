from django.conf import settings
from django.template import Context
from django.template.loader import get_template

from datetime import datetime, timedelta, date
import base64
import os

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.invoices.util import InvoiceManager

from models import Sponsor, PurchasedVoucher
from postgresqleu.confreg.models import PrepaidBatch, PrepaidVoucher
import postgresqleu.invoices.models as invoicemodels

def confirm_sponsor(sponsor, who):
	# Confirm a sponsor, including sending the confirmation email.
	# This will save the specified sponsor model as well, but the function
	# expects to be wrapped in external transaction handler.
	sponsor.confirmed = True
	sponsor.confirmedat = datetime.now()
	sponsor.confirmedby = who
	sponsor.save()

	msgtxt = get_template('confsponsor/mail/sponsor_confirmed.txt').render(Context({
		'sponsor': sponsor,
		'conference': sponsor.conference,
	}))
	for manager in sponsor.managers.all():
		send_simple_mail(sponsor.conference.sponsoraddr,
						 manager.email,
						 u"[{0}] Sponsorship confirmed".format(sponsor.conference),
						 msgtxt,
						 sendername=sponsor.conference.conferencename,
						 receivername=u'{0} {1}'.format(manager.first_name, manager.last_name))


class InvoiceProcessor(object):
	# Process invoices for sponsorship (this should include both automatic
	# and manual invoices, as long as they are created through the system)
	def process_invoice_payment(self, invoice):
		try:
			sponsor = Sponsor.objects.get(pk=invoice.processorid)
		except Sponsor.DoesNotExist:
			raise Exception("Could not find conference sponsor %s" % invoice.processorid)

		if sponsor.confirmed:
			# This sponsorship was already confirmed. Typical case for this is the contract
			# was signed manually, and then the invoice was generated. In this case, we just
			# don't care, so we return without updating the date of the confirmation.
			return

		confirm_sponsor(sponsor, "Invoice payment")

		conference = sponsor.conference

		send_simple_mail(conference.sponsoraddr,
						 conference.sponsoraddr,
						 "Confirmed sponsor: %s" % sponsor.name,
						 "The sponsor\n%s\nhas completed payment of the sponsorship invoice,\nand is now activated.\nBenefits are not claimed yet." % sponsor.name)

	# An invoice was canceled.
	def process_invoice_cancellation(self, invoice):
		try:
			sponsor = Sponsor.objects.get(pk=invoice.processorid)
		except Sponsor.DoesNotExist:
			raise Exception("Could not find conference sponsor %s" % invoice.processorid)

		if sponsor.confirmed:
			raise Exception("Cannot cancel this invoice, the sponsorship has already been marked as confirmed!")

		# Else the sponsor is not yet confirmed, so we can safely remove the invoice. We will leave the
		# sponsorship registration in place, so we can create a new one if we have to.
		sponsor.invoice = None
		sponsor.save()


	# Return the user to the sponsor page if they have paid.
	def get_return_url(self, invoice):
		try:
			sponsor = Sponsor.objects.get(pk=invoice.processorid)
		except Sponsor.DoesNotExist:
			raise Exception("Could not find conference sponsorship %s" % invoice.processorid)
		return "%s/events/sponsor/%s/" % (settings.SITEBASE_SSL, sponsor.id)


# Generate an invoice for sponsorship
def create_sponsor_invoice(user, user_name, name, address, conference, level, sponsorid):
	invoicerows = [
		['%s %s sponsorship' % (conference, level), 1, level.levelcost],
	]
	if conference.startdate < date.today() + timedelta(days=5):
		# If conference happens in the next 5 days, invoice is due immediately
		duedate = date.today()
	elif conference.startdate < date.today() + timedelta(days=30):
		# Less than 30 days before the conference, set the due date to
		# 5 days before the conference
		duedate = conference.startdate - timedelta(days=5)
	else:
		# More than 30 days before the conference, set the due date
		# to 30 days from now.
		duedate = datetime.now() + timedelta(days=30)

	manager = InvoiceManager()
	processor = invoicemodels.InvoiceProcessor.objects.get(processorname="confsponsor processor")
	i = manager.create_invoice(
		user,
		user.email,
		user_name,
		'%s\n%s' % (name, address),
		'%s sponsorship' % conference.conferencename,
		datetime.now(),
		duedate,
		invoicerows,
		processor = processor,
		processorid = sponsorid,
		bankinfo = True,
		accounting_account = settings.ACCOUNTING_CONFSPONSOR_ACCOUNT,
		accounting_object = conference.accounting_object,
		autopaymentoptions = False
	)
	i.allowedmethods = level.paymentmethods.all()
	return i


class VoucherInvoiceProcessor(object):
	# Process invoices for sponsor-ordered prepaid vouchers. This includes
	# actually creating the vouchers as necessary.
	def process_invoice_payment(self, invoice):
		try:
			pv = PurchasedVoucher.objects.get(pk=invoice.processorid)
		except PurchasedVoucher.DoesNotExist:
			raise Exception("Could not find voucher order %s" % invoice.processorid)

		if pv.batch:
			raise Exception("This voucher order has already been processed: %s" % invoice.processorid)

		# Set up the batch
		batch = PrepaidBatch(conference=pv.sponsor.conference,
							 regtype=pv.regtype,
							 buyer=pv.user,
							 buyername="{0} {1}".format(pv.user.first_name, pv.user.last_name),
							 sponsor=pv.sponsor)
		batch.save()

		for n in range(0, pv.num):
			v = PrepaidVoucher(conference=pv.sponsor.conference,
							   vouchervalue=base64.b64encode(os.urandom(37)).rstrip('='),
							   batch=batch)
			v.save()

		pv.batch = batch
		pv.save()

		send_simple_mail(pv.sponsor.conference.sponsoraddr,
						 pv.sponsor.conference.sponsoraddr,
						 "Sponsor %s purchased vouchers" % pv.sponsor.name,
						 "The sponsor\n%s\nhas purchased %s vouchers of type \"%s\".\n\n" % (pv.sponsor.name, pv.num, pv.regtype.regtype))

	# An invoice was canceled.
	def process_invoice_cancellation(self, invoice):
		try:
			pv = PurchasedVoucher.objects.get(pk=invoice.processorid)
		except PurchasedVoucher.DoesNotExist:
			raise Exception("Could not find voucher order %s" % invoice.processorid)

		if pv.batch:
			raise Exception("Cannot cancel this invoice, the order has already been processed!")

		# Order not confirmed yet, so we can just remove it
		pv.delete()

	# Return the user to the sponsor page if they have paid.
	def get_return_url(self, invoice):
		try:
			pv = PurchasedVoucher.objects.get(pk=invoice.processorid)
		except PurchasedVoucher.DoesNotExist:
			raise Exception("Could not find voucher order %s" % invoice.processorid)
		return "%s/events/sponsor/%s/" % (settings.SITEBASE_SSL, pv.sponsor.id)


# Generate an invoice for prepaid vouchers
def create_voucher_invoice(sponsor, user, rt, num):
	invoicerows = [
		['Voucher for "%s"' % rt.regtype, num, rt.cost]
		]

	manager = InvoiceManager()
	processor = invoicemodels.InvoiceProcessor.objects.get(processorname="confsponsor voucher processor")
	i = manager.create_invoice(
		user,
		user.email,
		user.first_name + ' ' + user.last_name,
		sponsor.invoiceaddr,
		'Prepaid vouchers for %s' % sponsor.conference.conferencename,
		datetime.now(),
		date.today(),
		invoicerows,
		processor = processor,
		bankinfo = False,
		accounting_account = settings.ACCOUNTING_CONFREG_ACCOUNT,
		accounting_object = sponsor.conference.accounting_object,
		autopaymentoptions = True
	)
	return i
