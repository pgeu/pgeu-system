#
# Script to post previosly unposted news to twitter
#
#

from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import slugify
from django.db import connection
from django.conf import settings
from django.utils import timezone

from datetime import datetime, timedelta
import sys
import time

from postgresqleu.newsevents.models import News
from postgresqleu.confreg.models import Conference, ConferenceNews, ConferenceTweetQueue, ConferenceIncomingTweet

from postgresqleu.util.messaging.twitter import Twitter


def news_tweets_queryset():
    return News.objects.filter(tweeted=False, datetime__gt=timezone.now() - timedelta(days=7), datetime__lt=timezone.now())


def conferences_with_tweets_queryset():
    return Conference.objects.filter(twittersync_active=True).extra(where=[
        "(EXISTS (SELECT 1 FROM confreg_conferencetweetqueue q WHERE q.conference_id=confreg_conference.id AND q.approved AND NOT q.sent) OR EXISTS (SELECT 1 FROM confreg_conferenceincomingtweet i WHERE i.conference_id=confreg_conference.id AND i.retweetstate=1))"
    ])


class Command(BaseCommand):
    help = 'Post to twitter'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=5)

        @classmethod
        def should_run(self):
            if settings.TWITTER_NEWS_TOKEN:
                if news_tweets_queryset().exists():
                    return True
            if conferences_with_tweets_queryset().exists():
                return True

            return False

    def handle(self, *args, **options):
        curs = connection.cursor()
        curs.execute("SELECT pg_try_advisory_lock(981273)")
        if not curs.fetchall()[0][0]:
            raise CommandError("Failed to get advisory lock, existing twitter_post process stuck?")

        err = False

        if settings.TWITTER_NEWS_TOKEN:
            tw = Twitter()

            for a in news_tweets_queryset().order_by('datetime'):
                # We hardcode 30 chars for the URL shortener. And then 10 to cover the intro and spacing.
                statusstr = "{0} {1}/news/{2}-{3}/".format(a.title[:140 - 40],
                                                           settings.SITEBASE,
                                                           slugify(a.title),
                                                           a.id)
                id, msg = tw.post_tweet(statusstr)
                if id:
                    a.tweeted = True
                    a.save()
                else:
                    err = True
                    self.stderr.write("Failed to post to twitter: %s" % msg)

                # Don't post more often than once / 10 seconds, to not trigger flooding detection.
                time.sleep(10)

        # Send off the conference twitter queue (which should normally only be one or two tweets, due to the filtering
        # on datetime.
        for c in conferences_with_tweets_queryset():
            tw = Twitter(c)

            for t in ConferenceTweetQueue.objects.filter(conference=c, approved=True, sent=False, datetime__lte=timezone.now()).order_by('datetime'):
                id, msg = tw.post_tweet(t.contents, t.image, t.replytotweetid)
                if id:
                    t.sent = True
                    t.tweetid = id
                    t.save(update_fields=['sent', 'tweetid', ])
                else:
                    err = True
                    self.stderr.write("Failed to post to twitter: %s" % msg)

                # Don't post more often than once / 10 seconds, to not trigger flooding detection.
                time.sleep(10)

            for t in ConferenceIncomingTweet.objects.filter(conference=c, retweetstate=1):
                ok, msg = tw.retweet(t.statusid)
                if ok:
                    t.retweetstate = 2
                    t.save(update_fields=['retweetstate'])
                else:
                    self.stderr.write("Failed to retweet: %s" % msg)

                time.sleep(2)

        if err:
            # Error message printed earlier, but we need to exit with non-zero exitcode
            # to flag the whole job as failed.
            sys.exit(1)
