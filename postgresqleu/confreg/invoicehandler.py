from models import ConferenceRegistration

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


	# Return the user to a page showing what happened as a result
	# of their payment. In our case, we just return the user directly
	# to the registration page.
	def get_return_url(self, invoice):
		# The processorid field contains our registration id
		try:
			reg = ConferenceRegistration.objects.get(pk=invoice.processorid)
		except ConferenceRegistration.DoesNotExist:
			raise Exception("Could not find conference registration %s" % invoice.processorid)
		return "https://www.postgresql.org/events/register/%s/" % reg.conference.urlname
