# Expire additional options on pending registration that have not
# been paid on time, so others can get those seats.
#
# Copyright (C) 2015, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.db import transaction

from collections import defaultdict
from io import StringIO


from postgresqleu.mailqueue.util import send_simple_mail

from postgresqleu.confreg.util import expire_additional_options
from postgresqleu.confreg.models import ConferenceRegistration


class Command(BaseCommand):
    help = 'Expire additional options on pending registrations'

    @transaction.atomic
    def handle(self, *args, **options):
        # Expiry of additional options is based on when the registration was last modified, and not
        # the actual additional option. But the 99.9% case is people who are not touching their
        # registration at all, so this is not a problem. If they go in and change their address,
        # they get an additional grace period only.
        #
        # We also don't expire any registrations that have an invoice or a bulk registration. Those
        # are handled by the invoice cancellation.
        #
        # Pending additional options make no difference here because they are not actually added
        # to the registration, and the pending order itself will be canceled along with the invoice.
        #
        # And no - the django ORM does not like to do date math in the WHERE clause, AFAICT, when the
        # values come from different tables.
        regs = ConferenceRegistration.objects.filter(payconfirmedat__isnull=True,
                                                     invoice__isnull=True,
                                                     bulkpayment__isnull=True,
                                                     additionaloptions__invoice_autocancel_hours__isnull=False,
        ).extra(
            where=["lastmodified < CURRENT_TIMESTAMP - confreg_conferenceadditionaloption.invoice_autocancel_hours * '1 hour'::interval", ]
        )

        expired = defaultdict(list)
        num = 0
        for r in regs:
            expired[r.conference].extend([(r.firstname + ' ' + r.lastname, x) for x in expire_additional_options(r)])
            num += len(expired[r.conference])

        if num:
            for conference, expired in list(expired.items()):
                s = StringIO()
                s.write("""The following additional options have been removed from pending
registrations (without invoice or bulk payment) based on the invoice
autocancel hours, to make room for other attendees:

""")
                for name, option in expired:
                    s.write("{0:<40}{1}\n".format(name, option))
                s.write("\n\n")
                send_simple_mail(conference.notifyaddr,
                                 conference.notifyaddr,
                                 'Additional options removed from pending registrations',
                                 s.getvalue(),
                                 sendername=conference.conferencename)
