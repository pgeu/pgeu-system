# Send queued attendee emails.
#

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.conf import settings

from datetime import timedelta

from postgresqleu.confreg.models import AttendeeMail, ConferenceRegistration
from postgresqleu.confreg.util import send_conference_mail
from postgresqleu.confreg.jinjafunc import render_sandboxed_template


class Command(BaseCommand):
    help = 'Send attendee emails'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=5)
        internal = True

        @classmethod
        def should_run(self):
            return AttendeeMail.objects.filter(sentat__lte=timezone.now(), sent=False).exists()

    @transaction.atomic
    def handle(self, *args, **options):
        for msg in AttendeeMail.objects.filter(sentat__lte=timezone.now(), sent=False):
            # By registration type
            attendees = set(ConferenceRegistration.objects.filter(conference=msg.conference, payconfirmedat__isnull=False, canceledat__isnull=True, regtype__regclass__attendeemail=msg))
            # By additional options
            attendees.update(ConferenceRegistration.objects.filter(conference=msg.conference, payconfirmedat__isnull=False, canceledat__isnull=True, additionaloptions__attendeemail=msg))
            # To direct attendees
            attendees.update(msg.registrations.all())
            # To volunteers
            if msg.tovolunteers:
                attendees.update(msg.conference.volunteers.all())
            # To checkin processors
            if msg.tocheckin:
                attendees.update(msg.conference.checkinprocessors.all())

            def _render_and_send(email, attendee, firstname, lastname):
                body = render_sandboxed_template(msg.message, dict({
                    'conference': msg.conference,
                    'attendee': attendee,
                    'firstname': firstname,
                    'lastname': lastname,
                }, **msg.extracontext))

                send_conference_mail(msg.conference,
                                     email,
                                     msg.subject,
                                     'confreg/mail/attendee_mail.txt',
                                     {
                                         'body': body,
                                         'linkback': True,
                                     },
                                     receivername=attendee.fullname if attendee else '{} {}'.format(firstname, lastname),
                )

            # Send to all regular recipients, where we can render a recipient specific version
            for a in attendees:
                _render_and_send(a.email, a, a.firstname, a.lastname)

            # Pending regs have no registration, but we can still get the name
            for p in msg.pending_regs.all():
                _render_and_send(p.email, None, p.first_name, p.last_name)

            msg.sent = True
            msg.save(update_fields=['sent'])
