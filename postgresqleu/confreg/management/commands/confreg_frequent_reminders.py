#
# Send frequent reminders using interfaces like twitter DMs
#
# For now this only means sending a reminder to speakers 10-15 minutes
# before their session begins.
#

from django.core.management.base import BaseCommand
from django.db import transaction, connection
from django.conf import settings

from datetime import datetime, timedelta

from postgresqleu.confreg.models import Conference, ConferenceSession
from postgresqleu.confreg.models import ConferenceRegistration

from postgresqleu.util.messaging.twitter import Twitter


class Command(BaseCommand):
    help = 'Send frequent conference reminders'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=5)

        @classmethod
        def should_run(self):
            return Conference.objects.filter(twitterreminders_active=True,
                                             startdate__lte=datetime.today() + timedelta(days=1),
                                             enddate__gte=datetime.today() - timedelta(days=1)) \
                                     .exclude(twitter_token='') \
                                     .exclude(twitter_secret='').exists()

    def handle(self, *args, **options):
        if not settings.TWITTER_CLIENT or not settings.TWITTER_CLIENTSECRET:
            return

        curs = connection.cursor()
        curs.execute("SELECT pg_try_advisory_lock(94012426)")
        if not curs.fetchall()[0][0]:
            raise CommandError("Failed to get advisory lock, existing frequent reminder process stuck?")

        # Only conferences that are actually running right now need to be considered.
        # Normally this is likely just one.
        # We can also filter for conferences that actually have reminders active.
        # Right now that's only twitter reminders, butin the future there cna be
        # more plugins.
        for conference in Conference.objects.filter(twitterreminders_active=True,
                                                    startdate__lte=datetime.today() + timedelta(days=1),
                                                    enddate__gte=datetime.today() - timedelta(days=1)) \
                                            .exclude(twitter_token='') \
                                            .exclude(twitter_secret=''):
            tw = Twitter(conference)
            with transaction.atomic():
                # Sessions that can take reminders (yes we could make a more complete join at one
                # step here, but that will likely fall apart later with more integrations anyway)
                for s in ConferenceSession.objects.select_related('room') \
                                                  .filter(conference=conference,
                                                          starttime__gt=datetime.now() - timedelta(hours=conference.timediff),
                                                          starttime__lt=datetime.now() - timedelta(hours=conference.timediff) + timedelta(minutes=15),
                                                          status=1,
                                                          reminder_sent=False):
                    for reg in ConferenceRegistration.objects.filter(
                            conference=conference,
                            attendee__speaker__conferencesession=s):

                        msg = """Hello! We'd like to remind you that your session "{0}" is starting soon (at {1}) in room {2}.""".format(
                            s.title,
                            s.starttime.strftime("%H:%M"),
                            s.room.roomname,
                        )
                        if reg.twittername:
                            # Twitter name registered, so send reminder
                            ok, code, err = tw.send_message(reg.twittername, msg)
                            if not ok and code != 150:
                                # Code 150 means trying to send DM to user not following us, so just
                                # ignore that one. Other errors should be shown.
                                self.stderr.write("Failed to send twitter DM to {0}: {1}".format(reg.twittername, err))

                    s.reminder_sent = True
                    s.save()
