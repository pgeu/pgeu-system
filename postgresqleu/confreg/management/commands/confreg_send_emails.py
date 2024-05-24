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

            # Pending registrations don't have a ConferenceRegistration object, so we need to extract just the parts we need.
            recipients = [(a.fullname, a.email) for a in attendees]
            recipients.extend([('{} {}'.format(u.first_name, u.last_name), u.email) for u in msg.pending_regs.all()])

            for fullname, email in recipients:
                send_conference_mail(msg.conference,
                                     email,
                                     msg.subject,
                                     'confreg/mail/attendee_mail.txt',
                                     {
                                         'body': msg.message,
                                         'linkback': True,
                                     },
                                     receivername=fullname,
                )
            msg.sent = True
            msg.save(update_fields=['sent'])
