#
# Post social media broadcast about news.
#
# This doesn't actually make a post -- it just places them in the
# outbound queue for the global social media script to handle.
#

# Copyright (C) 2019, PostgreSQL Europe

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.template.defaultfilters import slugify
from django.conf import settings

from datetime import timedelta

from postgresqleu.confreg.models import ConferenceNews, ConferenceHashtag
from postgresqleu.confreg.twitter import post_conference_social


class Command(BaseCommand):
    help = 'Schedule social media posts about conference news'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=5)
        internal = True

        @classmethod
        def should_run(self):
            # Any unposted news from a conference where the news is dated in the past (so that it
            # is actually visible), but not more than 7 days in the past (in which case we skip it).
            return ConferenceNews.objects.filter(tweeted=False, datetime__lt=timezone.now(), datetime__gt=timezone.now() - timedelta(days=7)).exists()

    @transaction.atomic
    def handle(self, *args, **options):
        for n in ConferenceNews.objects.filter(tweeted=False, datetime__lt=timezone.now(), datetime__gt=timezone.now() - timedelta(days=7)):
            statusstr = "{0} {1}/events/{2}/news/{3}-{4}/".format(
                n.title[:250 - 40],
                settings.SITEBASE,
                n.conference.urlname,
                slugify(n.title),
                n.id,
            )

            # If there are any auto-add hashtags defined for this conference, publish them
            hashtags = " ".join([h.hashtag for h in ConferenceHashtag.objects.filter(conference=n.conference, autoadd=True)])
            if hashtags:
                statusstr = '{}\n\n{}'.format(statusstr, hashtags)

            post_conference_social(n.conference, statusstr, approved=True)
            n.tweeted = True
            n.save()
