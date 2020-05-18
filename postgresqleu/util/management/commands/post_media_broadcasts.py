#
# Script to post previosly unposted news to social media
#


from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import slugify
from django.db import connection, transaction
from django.conf import settings
from django.utils import timezone

from datetime import datetime, timedelta
import sys

from postgresqleu.util.messaging import ProviderCache
from postgresqleu.util.messaging.sender import send_pending_posts


class Command(BaseCommand):
    help = 'Post to social media'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=5)

        @classmethod
        def should_run(self):
            return ConferenceTweetQueue.objects.filter(approved=True, sent=False, datetime__lte=timezone.now()).exists() or ConferenceIncomingTweet.objects.filter(retweetstate=1).exists()

    def handle(self, *args, **options):
        curs = connection.cursor()
        curs.execute("SELECT pg_try_advisory_lock(981279)")
        if not curs.fetchall()[0][0]:
            raise CommandError("Failed to get advisory lock, existing post_media_broadcasts process stuck?")

        providers = ProviderCache()

        ok, numposts, numreposts = send_pending_posts(providers)

        if numposts:
            print("Sent {} broadcast posts".format(numposts))
        if numreposts:
            print("Made {} broadcast reposts".format(numreposts))

        if not ok:
            sys.exit(1)
