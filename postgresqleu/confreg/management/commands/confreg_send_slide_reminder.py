# Send remainder to sessions speakers to upload their slides.
# after the conference ended.
#
# Intended to run on a daily basis or so, as it will keep repeating
# the reminders every time.
#
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from datetime import timedelta


from postgresqleu.confreg.models import Conference, ConferenceSession


from postgresqleu.confreg.util import send_conference_mail


class Command(BaseCommand):
    help = "upload slides after event"

    class ScheduledJob:
        scheduled_interval = timedelta(days=1)
        internal = True

    @transaction.atomic
    def handle(self, *args, **options):

        valid_conferences = filter(lambda c: c.needs_reminder, Conference.objects.filter(
            enddate__lte=timezone.now(),
            slide_upload_reminder_days__gt=0,
            ).extra(select={"needs_reminder": "EXISTS (SELECT 1 FROM confreg_conference WHERE enddate + slide_upload_reminder_days * interval '1 day' < now())"}))

        for conference in valid_conferences:
            self.remind_speakers(conference)

    def remind_speakers(self, conference):
        sessions = (
            ConferenceSession.objects.filter(conference=conference, status=1)
            .extra(
                select={
                    "has_slides": "EXISTS (SELECT 1 FROM confreg_conferencesessionslides WHERE session_id=confreg_conferencesession.id)",
                }
            )

        )

        for session in sessions:
            if session.has_slides:
                self.cancel_upload_reminder(conference)
            else:
                self.send_reminder_email(conference, session.speaker.all(), session)

    def cancel_upload_reminder(self, conference):
        conference.slide_upload_reminder_days = 0
        conference.save()

    def send_reminder_email(self, conference, speakers, session):
        for speaker in speakers:
            send_conference_mail(
                conference,
                speaker.user.email,
                "Your Slides".format(conference),
                "confreg/mail/speaker_remind_slides.txt",
                {
                    "conference": conference,
                    "session": session,
                },
                receivername=speaker.fullname,
            )
