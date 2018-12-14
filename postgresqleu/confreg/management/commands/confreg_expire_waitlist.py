#!/usr/bin/env python
#
# Expire waitlist offers that have expired, so others can get the
# seats.
#
# Copyright (C) 2015, PostgreSQL Europe
#
from django.core.management.base import BaseCommand
from django.db import transaction

from datetime import datetime

from postgresqleu.mailqueue.util import send_simple_mail, send_template_mail

from postgresqleu.confreg.models import RegistrationWaitlistEntry, RegistrationWaitlistHistory

class Command(BaseCommand):
    help = 'Expire conference waitlist offers'

    @transaction.atomic
    def handle(self, *args, **options):
        # Any entries that actually have an invoice will be canceled by the invoice
        # system, as the expiry time of the invoice is set synchronized. In this
        # run, we only care about offers that have not been picked up at all.
        wlentries = RegistrationWaitlistEntry.objects.filter(registration__payconfirmedat__isnull=True, registration__invoice__isnull=True, offerexpires__lt=datetime.now())

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
            send_template_mail(reg.conference.contactaddr,
                               reg.email,
                               'Your waitlist offer for {0}'.format(reg.conference.conferencename),
                               'confreg/mail/waitlist_expired.txt',
                               {
                                   'conference': reg.conference,
                                   'reg': reg,
                                   'offerexpires': w.offerexpires,
                               },
                               sendername = reg.conference.conferencename,
                               receivername = reg.fullname,
                           )

            # Now actually expire the offer
            w.offeredon = None
            w.offerexpires = None
            # Move the user to the back of the waitlist (we have a history entry for the
            # initial registration date, so it's still around)
            w.enteredon = datetime.now()

            w.save()
