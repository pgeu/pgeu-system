from django.conf import settings
from django.template import Context
from django.template.loader import get_template

from datetime import datetime, date, timedelta

from postgresqleu.mailqueue.util import send_simple_mail

from models import PrepaidVoucher, DiscountCode, RegistrationWaitlistHistory

def invoicerows_for_registration(reg, update_used_vouchers):
	# Return the rows that would be used to build an invoice for this
	# registration. Format is tuple of (description, num, cost)

	# Main conference registration
	r = [('%s - %s (%s)' % (reg.conference, reg.regtype.regtype, reg.email), 1, reg.regtype.cost)]

	# Any additional options
	for a in reg.additionaloptions.all():
		if a.cost > 0:
			r.append(('   %s' % a.name, 1, a.cost))

	# Any voucher if present
	if reg.vouchercode:
		try:
			v = PrepaidVoucher.objects.get(vouchervalue=reg.vouchercode, conference=reg.conference)
			if v.usedate:
				# Find a way to raise an exception here if the voucher is
				# already used? For now, we just ignore it.
				pass
			else:
				# Valid voucher found!
				if update_used_vouchers:
					v.usedate = datetime.now()
					v.user = reg
					v.save()
				# Add a row with the discount of the registration type
				r.append(('   Discount voucher %s...' % reg.vouchercode[:30], 1, -reg.regtype.cost))
		except PrepaidVoucher.DoesNotExist:
			# Nonexistant voucher code means discount code was used
			try:
				d = DiscountCode.objects.get(code=reg.vouchercode, conference=reg.conference)
				if d.validuntil and d.validuntil <= date.today():
					# Find a way to raise an exception here if the voucher is
					# expired. But it has already been checked in the form
					# submission step... But make sure not to apply it
					pass
				elif d.maxuses > 0 and d.registrations.count() >= d.maxuses:
					# Same goes for the count
					pass
				elif d.is_invoiced:
					# If it's been invoiced, it cannot be used anymore! Should only happen if one
					# of the above rules are true as well, but just in case somebody makes a change in the db.
					pass
				else:
					# Valid discount code found!
					selected_options = reg.additionaloptions.all()
					for o in d.requiresoption.all():
						if not o in selected_options:
							# Find a way to raise an exception here if
							# the voucher requires an option that is
							# not selected. But it has already been
							# checked in the form submission
							# step... But make sure not to apply it
							return r

					required_regtypes = d.requiresregtype.all()
					if required_regtypes:
						if not reg.regtype in required_regtypes:
							# See above about raising exception.
							return r

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
						r.append(('   Discount code %s' % d.code, 1, -discount))
			except DiscountCode.DoesNotExist:
				# An invalid voucher should never make it this far, but if it does
				# we'll just ignore it. Errors would've been given when the form
				# was saved.
				pass

	return r


def notify_reg_confirmed(reg):
	# This one was off the waitlist, so generate a history entry
	if hasattr(reg, 'registrationwaitlistentry'):
		RegistrationWaitlistHistory(waitlist=reg.registrationwaitlistentry,
									text="Completed registration from the waitlist").save()

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
					 receivername=u'{0} {1}'.format(reg.firstname, reg.lastname),
	)



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

		template = get_template('confreg/mail/additionaloption_expired.txt')

		send_simple_mail(reg.conference.contactaddr,
						 reg.email,
						 'Your pending registration for {0}'.format(reg.conference.conferencename),
						 template.render(Context({
							 'conference': reg.conference,
							 'reg': reg,
							 'options': expireset,
							 'optionscount': len(expireset),
							 'SITEBASE': settings.SITEBASE,
						 })),
						 sendername = reg.conference.conferencename,
						 receivername = u"{0} {1}".format(reg.firstname, reg.lastname))

		for ao in expireset:
			# Notify caller that this one is being expired
			expired_names.append(ao.name)
			# And actually expire it
			reg.additionaloptions.remove(ao)

		# And finally - save
		reg.save()

	return expired_names
