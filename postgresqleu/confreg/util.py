from datetime import datetime

from models import PrepaidVoucher

def invoicerows_for_registration(reg, update_used_vouchers):
	# Return the rows that would be used to build an invoice for this
	# registration. Format is tuple of (description, num, cost)

	# Main conference registration
	r = [('%s - %s (%s)' % (reg.conference, reg.regtype.regtype, reg.email), 1, reg.regtype.cost)]

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
			# An invalid voucher should never make it this far, but if it does
			# we'll just ignore it. Errors would've been given when the form
			# was saved.
			pass

	# Any additional options
	for a in reg.additionaloptions.all():
		if a.cost > 0:
			r.append(('   %s' % a.name, 1, a.cost))
	return r
