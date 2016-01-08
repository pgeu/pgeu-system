#!/usr/bin/env python
#
# Expire waitlist offers that have expired, so others can get the
# seats.
#
# Copyright (C) 2015, PostgreSQL Europe
#
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

from datetime import datetime

from django.template import Context
from django.template.loader import get_template

from postgresqleu.mailqueue.util import send_simple_mail

from postgresqleu.confreg.models import RegistrationWaitlistEntry, RegistrationWaitlistHistory

class Command(BaseCommand):
	help = 'Expire conference waitlist offers'

	@transaction.atomic
	def handle(self, *args, **options):
		# Any entries that actually have an invoice will be canceled by the invoice
		# system, as the expiry time of the invoice is set synchronized. In this
		# run, we only care about offers that have not been picked up at all.
		wlentries = RegistrationWaitlistEntry.objects.filter(registration__payconfirmedat__isnull=True, registration__invoice__isnull=True, offerexpires__lt=datetime.now())

		template = get_template('confreg/mail/waitlist_expired.txt')

		for w in wlentries:
			reg = w.registration

			# Create a history entry so we know exactly when it happened
			RegistrationWaitlistHistory(waitlist=w,
										text="Offer expired at {0}".format(w.offerexpires)).save()

			# Notify conference organizers
			send_simple_mail(reg.conference.contactaddr,
							 reg.conference.contactaddr,
								 'Waitlist expired',
								 u'User {0} {1} <{2}> did not complete the registration before the waitlist offer expired.'.format(reg.firstname, reg.lastname, reg.email),
								 sendername=reg.conference.conferencename)

			# Also send an email to the user
			send_simple_mail(reg.conference.contactaddr,
							 reg.email,
							 'Your waitlist offer for {0}'.format(reg.conference.conferencename),
							 template.render(Context({
								 'conference': reg.conference,
								 'reg': reg,
								 'offerexpires': w.offerexpires,
								 'SITEBASE': settings.SITEBASE_SSL,
								 })),
							 sendername = reg.conference.conferencename,
							 receivername = u"{0} {1}".format(reg.firstname, reg.lastname),
							 )

			# Now actually expire the offer
			w.offeredon = None
			w.offerexpires = None
			# Move the user to the back of the waitlist (we have a history entry for the
			# initial registration date, so it's still around)
			w.enteredon = datetime.now()

			w.save()
