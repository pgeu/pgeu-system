from django.conf import settings

from models import ConferenceRegistration, BulkPayment, PendingAdditionalOrder
from models import RegistrationWaitlistHistory
from util import notify_reg_confirmed, expire_additional_options

from datetime import datetime

class InvoiceProcessor(object):
	# Process invoices once they're getting paid
	#
	# In the case of conference registration, this means that we
	# flag the conference registration as confirmed.
	#
	# Since we lock the registration when the invoice is generated,
	# we don't actually need to verify that nothing has changed.
	#
	# All modifications are already wrapped in a django transaction
	def process_invoice_payment(self, invoice):
		# The processorid field contains our registration id
		try:
			reg = ConferenceRegistration.objects.get(pk=invoice.processorid)
		except ConferenceRegistration.DoesNotExist:
			raise Exception("Could not find conference registration %s" % invoice.processorid)

		if reg.payconfirmedat:
			raise Exception("Registration already paid")

		reg.payconfirmedat = datetime.today()
		reg.payconfirmedby = "Invoice paid"
		reg.save()
		notify_reg_confirmed(reg)

	# Process an invoice being canceled. This means we need to unlink
	# it from the registration. We don't actually remove the registration,
	# but it will automatically become "unlocked" for further edits.
	def process_invoice_cancellation(self, invoice):
		try:
			reg = ConferenceRegistration.objects.get(pk=invoice.processorid)
		except ConferenceRegistration.DoesNotExist:
			raise Exception("Could not find conference registration %s" % invoice.processorid)

		if reg.payconfirmedat:
			raise Exception("Registration already paid")

		# Unlink this invoice from the registration. This will automatically
		# "unlock" the registration
		reg.invoice = None
		reg.save()

		# If this registration holds any additional options that are about to expire, release
		# them for others to use at this point. (This will send an additional email to the
		# attendee automatically)
		expire_additional_options(reg)

		# If the registration was on the waitlist, put it back in the
		# queue.
		if hasattr(reg, 'registrationwaitlistentry'):
			wl = reg.registrationwaitlistentry
			RegistrationWaitlistHistory(waitlist=wl,
										text="Invoice was cancelled, moving back to waitlist").save()
			wl.offeredon = None
			wl.offerexpires = None
			wl.enteredon = datetime.now()
			wl.save()


	# Process an invoice being refunded. This means we need to unlink
	# it from the registration, and also unconfirm the registration.
	def process_invoice_refund(self, invoice):
		try:
			reg = ConferenceRegistration.objects.get(pk=invoice.processorid)
		except ConferenceRegistration.DoesNotExist:
			raise Exception("Could not find conference registration %s" % invoice.processorid)

		if not reg.payconfirmedat:
			raise Exception("Registration not paid, data is out of sync!")

		# Unlink this invoice from the registration, and remove the payment
		# confirmation. This will automatically "unlock" the registration.
		reg.invoice = None
		reg.payconfirmedat = None
		reg.payconfirmedby = None
		reg.save()

	# Return the user to a page showing what happened as a result
	# of their payment. In our case, we just return the user directly
	# to the registration page.
	def get_return_url(self, invoice):
		# The processorid field contains our registration id
		try:
			reg = ConferenceRegistration.objects.get(pk=invoice.processorid)
		except ConferenceRegistration.DoesNotExist:
			raise Exception("Could not find conference registration %s" % invoice.processorid)
		return "%s/events/register/%s/" % (settings.SITEBASE, reg.conference.urlname)




class BulkInvoiceProcessor(object):
	# Process invoices once they're getting paid
	#
	# In the case of conference bulk registrations, this means that we
	# flag all the related conference registrations as confirmed.
	#
	# Since we lock the registration when the invoice is generated,
	# we don't actually need to verify that nothing has changed.
	#
	# All modifications are already wrapped in a django transaction
	def process_invoice_payment(self, invoice):
		# The processorid field contains our bulkpayment id
		try:
			bp = BulkPayment.objects.get(pk=invoice.processorid)
		except ConferenceRegistration.DoesNotExist:
			raise Exception("Could not find bulk payment %s" % invoice.processorid)

		if bp.paidat:
			raise Exception("Bulk payment already paid")

		bp.paidat = datetime.today()

		# Confirm all related ones
		for r in bp.conferenceregistration_set.all():
			r.payconfirmedat = datetime.today()
			r.payconfirmedby = "Bulk paid"
			r.save()
			notify_reg_confirmed(r)

		bp.save()

	# Process an invoice being canceled. This means we need to unlink
	# it from the registration. We don't actually remove the registration,
	# but it will automatically become "unlocked" for further edits.
	def process_invoice_cancellation(self, invoice):
		try:
			bp = BulkPayment.objects.get(pk=invoice.processorid)
		except ConferenceRegistration.DoesNotExist:
			raise Exception("Could not find bulk payment %s" % invoice.processor)
		if bp.paidat:
			raise Exception("Bulk registration already paid")

		# Unlink this bulk payment from all registrations. This will
		# automatically unlock the registrations.

		for r in bp.conferenceregistration_set.all():
			r.bulkpayment = None
			r.save()

			# If this registration holds any additional options that are about to expire, release
			# them for others to use at this point. (This will send an additional email to the
			# attendee automatically)
			expire_additional_options(r)

		# Now actually *remove* the bulk payment record completely,
		# since it no longer contains anything interesting.
		bp.delete()

	# Process an invoice being refunded. This means we need to unlink
	# it from the registration, as well as remove the payment confirmation
	# from the registrations.
	def process_invoice_refund(self, invoice):
		try:
			bp = BulkPayment.objects.get(pk=invoice.processorid)
		except ConferenceRegistration.DoesNotExist:
			raise Exception("Could not find bulk payment %s" % invoice.processor)
		if not bp.paidat:
			raise Exception("Bulk registration not paid - things are out of sync")

		# Unlink this bulk payment from all registrations. This will
		# automatically unlock the registrations.

		for r in bp.conferenceregistration_set.all():
			r.bulkpayment = None
			r.payconfirmedat = None
			r.payconfirmedby = None
			r.save()

		# Now actually *remove* the bulk payment record completely,
		# since it no longer contains anything interesting.
		bp.delete()

	# Return the user to a page showing what happened as a result
	# of their payment. In our case, we just return the user directly
	# to the bulk payment page.
	def get_return_url(self, invoice):
		try:
			bp = BulkPayment.objects.get(pk=invoice.processorid)
		except ConferenceRegistration.DoesNotExist:
			raise Exception("Could not find bulk payment %s" % invoice.processor)
		return "%s/events/bulkpay/%s/%s/" % (settings.SITEBASE, bp.conference.urlname, invoice.processorid)



class AddonInvoiceProcessor(object):
	# Process invoices for additional options added to an existing
	# registration.
	#
	# Since we lock the registration when the invoice is generated,
	# we don't actually need to verify that nothing has changed.
	#
	# All modifications are already wrapped in a django transaction
	def process_invoice_payment(self, invoice):
		try:
			order = PendingAdditionalOrder.objects.get(pk=invoice.processorid)
		except PendingAdditionalOrder.DoesNotExist:
			raise Exception("Could not find additional options order %s!" % invoice.processorid)

		if order.payconfirmedat:
			raise Exception("Additional options already paid")

		order.payconfirmedat = datetime.today()
		if order.newregtype:
			order.reg.regtype = order.newregtype

		for o in order.options.all():
			order.reg.additionaloptions.add(o)

		order.reg.save()
		order.save()

	def process_invoice_cancellation(self, invoice):
		try:
			order = PendingAdditionalOrder.objects.get(pk=invoice.processorid)
		except PendingAdditionalOrder.DoesNotExist:
			raise Exception("Could not find additional options order %s!" % invoice.processorid)

		# We just remove the entry completely, as there is no "unlocking"
		# here.
		order.delete()

	def process_invoice_refund(self, invoice):
		raise Exception("Don't know how to process refunds for this!")

	# Return the user to their dashboard
	def get_return_url(self, invoice):
		try:
			order = PendingAdditionalOrder.objects.get(pk=invoice.processorid)
		except PendingAdditionalOrder.DoesNotExist:
			raise Exception("Could not find additional options order %s!" % invoice.processorid)

		return "%s/events/register/%s/" % (settings.SITEBASE, order.reg.conference.urlname)
