#
# Script to fetch incoming social media posts
#


from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from datetime import timedelta
import sys

from postgresqleu.util.messaging import get_messaging
from postgresqleu.util.messaging.common import store_incoming_post

from postgresqleu.confreg.models import MessagingProvider


class Command(BaseCommand):
    help = 'Fetch from social media'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=15)

        @classmethod
        def should_run(self):
            return MessagingProvider.objects.filter(active=True, series__isnull=False, route_incoming__isnull=False).exists()

    def handle(self, *args, **options):
        curs = connection.cursor()
        curs.execute("SELECT pg_try_advisory_lock(981231)")
        if not curs.fetchall()[0][0]:
            raise CommandError("Failed to get advisory lock, existing fetch_media_posts process stuck?")

        err = False

        for provider in MessagingProvider.objects.filter(active=True, series__isnull=False, route_incoming__isnull=False):
            impl = get_messaging(provider)

            polltime = timezone.now()
            num = 0
            try:
                with transaction.atomic():
                    for post in impl.poll_public_posts(provider.public_lastpoll, provider.public_checkpoint):
                        # Update our checkpoint *first*, if it happens that we have already
                        # seen everything.
                        provider.public_checkpoint = max(provider.public_checkpoint, post['id'])

                        if store_incoming_post(provider, post):
                            num += 1
                    # Always save last polled time, and updated checkpoint if it changed
                    provider.public_lastpoll = polltime
                    provider.save(update_fields=['public_checkpoint', 'public_lastpoll'])
                if num:
                    print("Polled {} new posts from {}".format(num, provider))
            except Exception as e:
                print("Failed to poll {}: {}".format(provider, e))
                err = True

        if err:
            # Error message printed earlier, but we need to exit with non-zero exitcode
            # to flag the whole job as failed.
            sys.exit(1)
