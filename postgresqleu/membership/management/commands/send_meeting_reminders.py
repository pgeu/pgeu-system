#
# Send meeting reminder emails
#

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from datetime import timedelta

from postgresqleu.membership.models import MeetingReminder, get_config
from postgresqleu.mailqueue.util import send_template_mail


class Command(BaseCommand):
    help = 'Send meeting reminders'

    class ScheduledJob:
        internal = True
        scheduled_interval = timedelta(minutes=15)

        @classmethod
        def should_run(self):
            return MeetingReminder.objects.filter(sentat__isnull=True, sendat__lte=timezone.now()).exists()

    @transaction.atomic
    def handle(self, *args, **options):
        cfg = get_config()

        for r in MeetingReminder.objects.select_related('meeting').filter(sentat__isnull=True,
                                                                          sendat__lte=timezone.now()):
            for a in r.meeting.get_all_attendees().select_related('user'):
                send_template_mail(
                    cfg.sender_email,
                    a.user.email,
                    "Upcoming meeting: {}".format(r.meeting.name),
                    'membership/mail/meeting_reminder.txt',
                    {
                        'meeting': r.meeting,
                        'member': a,
                    },
                    sendername=cfg.sender_name,
                    receivername=a.fullname,
                )
            r.sentat = timezone.now()
            r.save()
