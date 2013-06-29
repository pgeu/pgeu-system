from django.conf import settings

from models import ConferenceRegistration, BulkPayment

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


	# Return the user to a page showing what happened as a result
	# of their payment. In our case, we just return the user directly
	# to the registration page.
	def get_return_url(self, invoice):
		# The processorid field contains our registration id
		try:
			reg = ConferenceRegistration.objects.get(pk=invoice.processorid)
		except ConferenceRegistration.DoesNotExist:
			raise Exception("Could not find conference registration %s" % invoice.processorid)
		return "%s/events/register/%s/" % (settings.SITEBASE_SSL, reg.conference.urlname)




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
		return "%s/events/bulkpay/%s/%s/" % (settings.SITEBASE_SSL, reg.conference.urlname, invoice.processorid)
