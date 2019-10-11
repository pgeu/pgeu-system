#
# Fetch incoming twitter posts (if any)
#

from django.core.management.base import BaseCommand
from django.db import transaction, connection
from django.db.models import Max
from django.conf import settings

from datetime import datetime, timedelta
import dateutil.parser

from postgresqleu.confreg.models import Conference, ConferenceIncomingTweet, ConferenceTweetQueue

from postgresqleu.util.messaging.twitter import Twitter


class Command(BaseCommand):
    help = 'Fetch incoming tweets'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=5)

        @classmethod
        def should_run(self):
            return Conference.objects.filter(twitterincoming_active=True) \
                                     .exclude(twitter_token='') \
                                     .exclude(twitter_secret='').exists()

    def handle(self, *args, **options):
        if not settings.TWITTER_CLIENT or not settings.TWITTER_CLIENTSECRET:
            return

        curs = connection.cursor()
        curs.execute("SELECT pg_try_advisory_lock(94032416)")
        if not curs.fetchall()[0][0]:
            raise CommandError("Failed to get advisory lock, existing tweet-fetcher stuck?")

        for conference in Conference.objects.filter(twitterincoming_active=True) \
                                            .exclude(twitter_token='') \
                                            .exclude(twitter_secret=''):
            tw = Twitter(conference)

            maxid = ConferenceIncomingTweet.objects.filter(conference=conference).aggregate(Max('statusid'))['statusid__max']

            with transaction.atomic():
                # Fetch anythning incoming
                r = tw.get_timeline('mentions', maxid)
                if r:
                    for tj in r:
                        if ConferenceIncomingTweet.objects.filter(statusid=tj['id']).exists():
                            # Just skip duplicates
                            continue
                        if ConferenceTweetQueue.objects.filter(tweetid=tj['id']).exists():
                            # Also skip if we hit one of our own generated tweets
                            continue

                        it = ConferenceIncomingTweet(
                            conference=conference,
                            statusid=tj['id'],
                            created=dateutil.parser.parse(tj['created_at']),
                            text=tj['full_text'],
                            replyto_statusid=tj['in_reply_to_status_id'],
                            author_name=tj['user']['name'],
                            author_screenname=tj['user']['screen_name'],
                            author_id=tj['user']['id'],
                            author_image_url=tj['user']['profile_image_url_https'],
                        )
                        if tj['is_quote_status']:
                            it.quoted_statusid = tj['quoted_status_id']
                            it.quoted_text = tj['quoted_status']['full_text']
                            it.quoted_permalink = tj['quoted_status_permalink']
                        it.save()
