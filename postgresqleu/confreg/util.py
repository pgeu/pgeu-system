from django.conf import settings
from django.contrib.auth.models import User

from datetime import datetime, date, timedelta
from decimal import Decimal

from postgresqleu.mailqueue.util import send_simple_mail, send_template_mail
from postgresqleu.util.random import generate_random_token

from models import PrepaidVoucher, DiscountCode, RegistrationWaitlistHistory
from models import ConferenceRegistration

class InvoicerowsException(Exception):
	pass

def invoicerows_for_registration(reg, update_used_vouchers):
	# Return the rows that would be used to build an invoice for this
	# registration. Format is tuple of (description, num, cost)

	# Main conference registration
	r = [['%s - %s' % (reg.email, reg.regtype.regtype),
		  1,
		  reg.regtype.cost,
		  reg.conference.vat_registrations,
		  ]]

	# Any additional options
	for a in reg.additionaloptions.all():
		if a.cost > 0:
			r.append(['   %s' % a.name, 1, a.cost, reg.conference.vat_registrations])

	# Any voucher if present
	if reg.vouchercode:
		try:
			v = PrepaidVoucher.objects.get(vouchervalue=reg.vouchercode, conference=reg.conference)
			if v.usedate:
				# Find a way to raise an exception here if the voucher is
				# already used? For now, we just ignore it.
				raise InvoicerowsException("Prepaid voucher already used")
			else:
				# Valid voucher found!
				if update_used_vouchers:
					v.usedate = datetime.now()
					v.user = reg
					v.save()
				# Add a row with the discount of the registration type
				r.append(['   Discount voucher %s...' % reg.vouchercode[:30], 1, -reg.regtype.cost, reg.conference.vat_registrations])
		except PrepaidVoucher.DoesNotExist:
			# Nonexistant voucher code means discount code was used
			try:
				d = DiscountCode.objects.get(code=reg.vouchercode, conference=reg.conference)
				if d.validuntil and d.validuntil < date.today():
					raise InvoicerowsException("Discount code is no longer valid")
				elif d.maxuses > 0 and d.registrations.count() >= d.maxuses:
					raise InvoicerowsException("Discount code does not have enough remaining instances")
				elif d.is_invoiced:
					raise InvoicerowsException("Discount code has already been invoiced and is no longer valid")
				else:
					# Valid discount code found!
					selected_options = reg.additionaloptions.all()
					for o in d.requiresoption.all():
						if not o in selected_options:
							raise InvoicerowsException(u"Discount code requires option {0}".format(o.name))

					required_regtypes = d.requiresregtype.all()
					if required_regtypes:
						if not reg.regtype in required_regtypes:
							raise InvoicerowsException(u"Discount code requires registration types {0}".format(u",".join(required_regtypes)))

					if update_used_vouchers:
						d.registrations.add(reg)
						d.save()
					# Add a row with the discount
					current_total = sum([rr[2] for rr in r])
					discount = 0
					if d.discountamount:
						# Fixed amount discount
						discount = d.discountamount > current_total and current_total or d.discountamount
					else:
						# Percentage discount. Can be either off the total or just the reg
						if d.regonly:
							discount = reg.regtype.cost*d.discountpercentage/100
						else:
							discount = current_total*d.discountpercentage/100
					if discount > 0:
						r.append(['   Discount code %s' % d.code, 1, -discount, reg.conference.vat_registrations])
			except DiscountCode.DoesNotExist:
				raise InvoicerowsException("Invalid voucher code")
	return r


def notify_reg_confirmed(reg, updatewaitlist=True):
	# This one was off the waitlist, so generate a history entry
	if updatewaitlist and hasattr(reg, 'registrationwaitlistentry'):
		RegistrationWaitlistHistory(waitlist=reg.registrationwaitlistentry,
									text="Completed registration from the waitlist").save()

	# If this registration has no user attached to it, it means that
	# it was a "register for somebody else". In this case we need to
	# send the user an email with information that otherwise would not
	# be available. This means that the user will get two separate
	# emails in case welcome emails is enabled, but that is necessary
	# since we need to include links and things in this email.
	if not reg.attendee:
		# First we see if we can just find a user match on email, this
		# being a user that has not already registered for this
		# conference.
		found = False
		try:
			u = User.objects.get(email=reg.email)
			if not ConferenceRegistration.objects.filter(conference=reg.conference, attendee=u).exists():
				# Found user by this id, not used yet, so attach it
				# to their account.
				reg.attendee = u
				reg.save()
				found = True
		except User.DoesNotExist:
			pass

		if not found:
			# User not found, so we use the random token and send it
			# to ask them to attach their account to this registration.
			send_template_mail(reg.conference.contactaddr,
							   reg.email,
							   "Your registration for {0}".format(reg.conference),
							   'confreg/mail/regmulti_attach.txt',
							   {
								   'conference': reg.conference,
								   'reg': reg,
							   },
							   sendername=reg.conference.conferencename,
							   receivername=reg.fullname,
			)

	# Do we need to send the welcome email?
	if not reg.conference.sendwelcomemail:
		return

	# Ok, this attendee needs a notification. For now we don't support
	# any string replacements in it, maybe in the future.
	send_simple_mail(reg.conference.contactaddr,
					 reg.email,
					 "[{0}] Registration complete".format(reg.conference),
					 reg.conference.welcomemail,
					 sendername=reg.conference.conferencename,
					 receivername=reg.fullname,
	)


def cancel_registration(reg):
	# Verify that we're only canceling a real registration
	if not reg.payconfirmedat:
		raise Exception("Registration not paid, data is out of sync!")

	# If we sent a welcome mail, also send a goodbye mail
	if reg.conference.sendwelcomemail:
		send_template_mail(reg.conference.contactaddr,
						   reg.email,
						   "[{0}] Registration canceled".format(reg.conference),
						   'confreg/mail/reg_canceled.txt',
						   {
							   'conference': reg.conference,
							   'reg': reg,
						   },
						   sendername=reg.conference.conferencename,
						   receivername=reg.fullname,
		)

	# Now actually delete the reg. Start by unlinking things that might be there.
	if reg.vouchercode:
		if PrepaidVoucher.objects.filter(user=reg).exists():
			v = PrepaidVoucher.objects.get(user=reg)
			v.user = None
			v.usedate = None
			v.save()
		elif DiscountCode.objects.filter(registrations=reg).exists():
			d = DiscountCode.objects.get(registrations=reg)
			d.registrations.remove(reg)
			d.save()
	reg.invoice = None
	reg.payconfirmedat = None
	reg.payconfirmedby = None
	reg.save()

	# Once unlinked, remove the registration as well. If we don't
	# do this, the user will get notifications to remember to
	# complete their registration in the future, and that will be
	# confusing.
	reg.delete()



def get_invoice_autocancel(*args):
	# Each argument is expected to be an integer with number of hours,
	# or None if there is no limit
	hours = [a for a in args if not a is None]
	if hours:
		return datetime.now() + timedelta(hours=min(hours))
	else:
		return None


def expire_additional_options(reg):
	# If there are any additional options on this registrations that are untouched for
	# longer than the invoice autocancel period, expire them. Send an email to the user
	# being expired (expects to run within a transaction).
	# Returns the list of options expired for this particular user.

	hours = int(round((datetime.now() - reg.lastmodified).total_seconds()/3600))
	expireset = list(reg.additionaloptions.filter(invoice_autocancel_hours__isnull=False,
												  invoice_autocancel_hours__lt=hours))

	expired_names = []
	if expireset:
		# We have something expired. Step one is to send an email about it, based on a
		# template. (It's a bit inefficient to re-parse the template every time, but
		# we don't expire these things very often, so we don't care)

		if reg.attendee:
			send_template_mail(reg.conference.contactaddr,
							   reg.email,
							   'Your pending registration for {0}'.format(reg.conference.conferencename),
							   'confreg/mail/additionaloption_expired.txt',
							   {
								   'conference': reg.conference,
								   'reg': reg,
								   'options': expireset,
								   'optionscount': len(expireset),
							   },
							   sendername = reg.conference.conferencename,
							   receivername = reg.fullname,
			)

		for ao in expireset:
			# Notify caller that this one is being expired
			expired_names.append(ao.name)
			# And actually expire it
			reg.additionaloptions.remove(ao)

		# And finally - save
		reg.save()

	return expired_names
