#
# Send frequent reminders using direct message
#
# For now this only means sending a reminder to speakers 10-15 minutes
# before their session begins.
#

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from datetime import timedelta

from postgresqleu.confreg.models import Conference, ConferenceSession
from postgresqleu.confreg.models import ConferenceRegistration
from postgresqleu.confreg.util import get_conference_or_404

from postgresqleu.util.time import today_global
from postgresqleu.util.messaging.util import send_reg_direct_message, send_private_broadcast


class Command(BaseCommand):
    help = 'Send frequent conference reminders'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=5)
        internal = True

        @classmethod
        def should_run(self):
            # We check for conferences to run at two days before and two days after to cover
            # any extreme timezone differences.
            return Conference.objects.filter(startdate__lte=today_global() + timedelta(days=2),
                                             enddate__gte=today_global() - timedelta(days=2)).exists()

    def handle(self, *args, **options):
        # Only conferences that are actually running right now need to be considered.
        # Normally this is likely just one.
        for conference in Conference.objects.filter(startdate__lte=today_global() + timedelta(days=2),
                                                    enddate__gte=today_global() - timedelta(days=2)):

            # Re-get the conference object to switch the timezone for django
            conference = get_conference_or_404(conference.urlname)

            with transaction.atomic():
                # Sessions that can take reminders
                for s in ConferenceSession.objects.select_related('room') \
                                                  .filter(conference=conference,
                                                          starttime__gt=timezone.now(),
                                                          starttime__lt=timezone.now() + timedelta(minutes=15),
                                                          status=1,
                                                          reminder_sent=False):

                    send_private_broadcast(conference,
                                           'The session "{0}" will start soon (at {1}){2}'.format(
                                               s.title,
                                               timezone.localtime(s.starttime).strftime("%H:%M"),
                                               s.room and " in room {}".format(s.room) or '',
                                           ),
                                           expiry=timedelta(minutes=15))

                    # Now also send DM reminders out to the speakers who have registered to get one
                    for reg in ConferenceRegistration.objects.filter(
                            conference=conference,
                            attendee__speaker__conferencesession=s):

                        msg = """Hello! We'd like to remind you that your session "{0}" is starting soon (at {1}) in room {2}.""".format(
                            s.title,
                            timezone.localtime(s.starttime).strftime("%H:%M"),
                            s.room and s.room.roomname or 'unknown',
                        )

                        # Send the message. Make it expire in 15 minutes, because that's after
                        # the session started anyway.
                        send_reg_direct_message(reg, msg, expiry=timedelta(minutes=15))

                    s.reminder_sent = True
                    s.save()
