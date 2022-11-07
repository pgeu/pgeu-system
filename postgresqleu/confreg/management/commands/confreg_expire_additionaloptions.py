# Expire additional options on pending registration that have not
# been paid on time, so others can get those seats.
#
# Copyright (C) 2015, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.db import transaction

from collections import defaultdict
from io import StringIO
from datetime import timedelta


from postgresqleu.util.time import today_global

from postgresqleu.confreg.util import expire_additional_options, send_conference_notification
from postgresqleu.confreg.models import Conference, ConferenceRegistration


class Command(BaseCommand):
    help = 'Expire additional options on pending registrations'

    class ScheduledJob:
        scheduled_interval = timedelta(hours=4)
        internal = True

        @classmethod
        def should_run(self):
            # Are there any conferences open for registration, conference is still in the future,
            # that have additional options with autocancel set
            return Conference.objects.filter(registrationopen=True,
                                             conferenceadditionaloption__invoice_autocancel_hours__isnull=False,
                                             enddate__gt=today_global() + timedelta(days=1),
            ).exists()

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
                send_conference_notification(
                    conference,
                    'Additional options removed from pending registrations',
                    s.getvalue(),
                )
