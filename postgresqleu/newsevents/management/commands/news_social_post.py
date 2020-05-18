#
# Make social media posts about news
#
# (actually just writes it to the queue for the next job to pick up)
#

from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import slugify
from django.db import transaction
from django.conf import settings
from django.utils import timezone

from datetime import timedelta

from postgresqleu.newsevents.models import News
from postgresqleu.confreg.models import ConferenceTweetQueue, MessagingProvider


class Command(BaseCommand):
    help = 'Post news to social media'

    class ScheduledJob:
        internal = True
        scheduled_interval = timedelta(minutes=5)

        @classmethod
        def should_run(self):
            return MessagingProvider.objects.filter(series__isnull=True).exists() and \
                News.objects.filter(tweeted=False, datetime__gt=timezone.now() - timedelta(days=7), datetime__lt=timezone.now()).exists()

    @transaction.atomic
    def handle(self, *args, **options):
        for n in News.objects.filter(tweeted=False, datetime__gt=timezone.now() - timedelta(days=7), datetime__lt=timezone.now()):
            # We hardcode 30 chars for the URL shortener. And then 10 to cover the intro and spacing.
            statusstr = "{0} {1}/news/{2}-{3}/".format(n.title[:140 - 40],
                                                       settings.SITEBASE,
                                                       slugify(n.title),
                                                       n.id)
            ConferenceTweetQueue(
                conference=None,
                contents=statusstr,
                approved=True,
                datetime=n.datetime,
            ).save()

            n.tweeted = True
            n.save()
