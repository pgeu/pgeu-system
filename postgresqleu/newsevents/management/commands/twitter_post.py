#
# Script to post previosly unposted news to twitter
#
#

from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import slugify
from django.db import connection
from django.conf import settings

from datetime import datetime, timedelta
import time

from postgresqleu.newsevents.models import News
from postgresqleu.confreg.models import Conference, ConferenceNews, ConferenceTweetQueue

from postgresqleu.util.messaging.twitter import Twitter

class Command(BaseCommand):
    help = 'Post to twitter'

    def handle(self, *args, **options):
        curs = connection.cursor()
        curs.execute("SELECT pg_try_advisory_lock(981273)")
        if not curs.fetchall()[0][0]:
            raise CommandError("Failed to get advisory lock, existing twitter_post process stuck?")

        if settings.TWITTER_NEWS_TOKEN:
            articles = list(News.objects.filter(tweeted=False, datetime__gt=datetime.now()-timedelta(days=7), datetime__lt=datetime.now()).order_by('datetime'))
        else:
            articles = []

        if articles:
            tw = Twitter()

            for a in articles:
                # We hardcode 30 chars for the URL shortener. And then 10 to cover the intro and spacing.
                statusstr = u"{0} {1}/news/{2}-{3}/".format(a.title[:140-40],
                                                            settings.SITEBASE,
                                                            slugify(a.title),
                                                            a.id)
                ok, msg = tw.post_tweet(statusstr)
                if ok:
                    a.tweeted = True
                    a.save()
                else:
                    print("Failed to post to twitter: %s" % msg)

                # Don't post more often than once / 10 seconds, to not trigger flooding.
                time.sleep(10)


        # Find which conferences to tweet from. We will only put out one tweet for each
        # conference, expecting to be called again in 5 minutes or so to put out the
        # next one.
        n = datetime.now().time()
        for c in Conference.objects.filter(twittersync_active=True,
                                           twitter_timewindow_start__lt=n,
                                           twitter_timewindow_end__gt=n).extra(where=[
                                               "EXISTS (SELECT 1 FROM confreg_conferencenews n WHERE n.conference_id=confreg_conference.id AND (NOT tweeted) AND datetime > now()-'7 days'::interval AND datetime < now()) OR EXISTS (SELECT 1 FROM confreg_conferencetweetqueue q WHERE q.conference_id=confreg_conference.id)"
                                           ]):
            tw = Twitter(c)

            al = list(ConferenceNews.objects.filter(conference=c, tweeted=False, datetime__gt=datetime.now()-timedelta(days=7), datetime__lt=datetime.now(), conference__twittersync_active=True).order_by('datetime')[:1])
            if al:
                a = al[0]
                statusstr = u"{0} {1}##{2}".format(a.title[:250-40],
                                                   c.confurl,
                                                   a.id)
                ok, msg = tw.post_tweet(statusstr)
                if ok:
                    a.tweeted = True
                    a.save()
                    continue
                else:
                    print("Failed to post to twitter: %s" % msg)

            tl = list(ConferenceTweetQueue.objects.filter(conference=c).order_by('datetime')[:1])
            if tl:
                t = tl[0]
                ok, msg = tw.post_tweet(t.contents)
                if ok:
                    t.delete()
                    continue
                else:
                    print("Failed to post to twitter: %s" % msg)

