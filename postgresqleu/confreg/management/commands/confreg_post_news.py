#
# Post tweets about news.
#
# This doesn't actually post the tweets -- it just places them in the
# outbound queue for the global twitter posting script to handle.
#

# Copyright (C) 2019, PostgreSQL Europe

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.template.defaultfilters import slugify
from django.conf import settings

from datetime import timedelta

from postgresqleu.confreg.models import ConferenceNews
from postgresqleu.confreg.twitter import post_conference_tweet


class Command(BaseCommand):
    help = 'Schedule tweets about conference news'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=10)
        internal = True

        @classmethod
        def should_run(self):
            # Any untweeted news from a conference with twitter active where the news is dated in the past (so that it
            # is actually visible), but not more than 7 days in the past (in which case we skip it).
            return ConferenceNews.objects.filter(tweeted=False, conference__twittersync_active=True, datetime__lt=timezone.now(), datetime__gt=timezone.now() - timedelta(days=7)).exists()

    @transaction.atomic
    def handle(self, *args, **options):
        for n in ConferenceNews.objects.filter(tweeted=False, conference__twittersync_active=True, datetime__lt=timezone.now(), datetime__gt=timezone.now() - timedelta(days=7)):
            statusstr = "{0} {1}/events/{2}/news/{3}-{4}/".format(
                n.title[:250 - 40],
                settings.SITEBASE,
                n.conference.urlname,
                slugify(n.title),
                n.id,
            )
            post_conference_tweet(n.conference, statusstr, approved=True)
            n.tweeted = True
            n.save()
