#
# Post tweets about news.
#
# This doesn't actually post the tweets -- it just places them in the
# outbound queue for the global twitter posting script to handle.
#

# Copyright (C) 2019, PostgreSQL Europe

from django.core.management.base import BaseCommand
from django.db import transaction

from datetime import datetime, timedelta

from postgresqleu.confreg.models import ConferenceNews, ConferenceTweetQueue


class Command(BaseCommand):
    help = 'Schedule tweets about conference news'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=10)
        internal = True

        @classmethod
        def should_run(self):
            # Any untweeted news from a conference with twitter active where the news is dated in the past (so that it
            # is actually visible), but not more than 7 days in the past (in which case we skip it).
            return ConferenceNews.objects.filter(tweeted=False, conference__twittersync_active=True, datetime__lt=datetime.now(), datetime__gt=datetime.now() - timedelta(days=7)).exists()

    @transaction.atomic
    def handle(self, *args, **options):
        for n in ConferenceNews.objects.filter(tweeted=False, conference__twittersync_active=True, datetime__lt=datetime.now(), datetime__gt=datetime.now() - timedelta(days=7)):
            statusstr = "{0} {1}##{2}".format(n.title[:250 - 40],
                                              n.conference.confurl,
                                              n.id)
            ConferenceTweetQueue(
                conference=n.conference,
                contents=statusstr,
                approved=True,
            ).save()
            n.tweeted = True
            n.save()
