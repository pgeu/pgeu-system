from django.conf import settings

from models import Member, MemberLog

from datetime import datetime, timedelta, date

class InvoiceProcessor(object):
	# Process invoices once they're getting paid
	#
	# In the case of membership, that simply means extending the
	# membership.
	def process_invoice_payment(self, invoice):
		# We'll get the member from the processorid
		try:
			member = Member.objects.get(pk=invoice.processorid)
		except member.DoesNotExist:
			raise Exception ("Could not find member id %s for invoice!" % invoice.processorid)

		# The invoice is paid, so it's no longer active!
		# It'll still be in the archive, of course, but not linked from the
		# membership record.
		member.activeinvoice = None

		# Extend the membership. If already paid to a date in the future,
		# extend from that date. Otherwise, from today.
		if member.paiduntil and member.paiduntil > date.today():
			member.paiduntil = member.paiduntil + timedelta(days=2*365)
		else:
			member.paiduntil = date.today()+timedelta(days=2*365)
		member.expiry_warning_sent = None

		# If the member isn't already a member, set todays date as the
		# starting date.
		if not member.membersince:
			member.membersince = date.today()

		member.save()

		# Create a log record too, and save it
		MemberLog(member=member, timestamp=datetime.now(), message="Payment for 2 years received, membership extended to %s" % member.paiduntil).save()

	# Process an invoice being canceled. This means we need to unlink
	# it from the membership.
	def process_invoice_cancellation(self, invoice):
		# We'll get the member from the processorid
		try:
			member = Member.objects.get(pk=invoice.processorid)
		except member.DoesNotExist:
			raise Exception ("Could not find member id %s for invoice!" % invoice.processorid)

		# Just remove the active invoice
		member.activeinvoice = None
		member.save()

	# We don't implement this yet
	def process_invoice_refund(self, invoice):
		raise Exception("Unable to refund membership invoices at this time")

	# Return the user to a page showing what happened as a result
	# of their payment. In our case, we just return the user directly
	# to the membership page.
	def get_return_url(self, invoice):
		return "%s/membership/" % settings.SITEBASE_SSL
