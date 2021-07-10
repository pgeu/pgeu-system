#
# Expire temporary API tokens
#
# These tokens are only valid for 5 minutes and this is both validated
# and cleaned up on API calls, so this script will only clean up tokens
# of aborted sessions. Because of that, we don't have to run it very often.
#

# Copyright (C) 2021, PostgreSQL Europe

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from datetime import timedelta

from postgresqleu.confreg.models import ConferenceRegistrationTemporaryToken


class Command(BaseCommand):
    help = 'Remove expired temporary tokens'

    class ScheduledJob:
        scheduled_interval = timedelta(hours=24)
        internal = True

        @classmethod
        def should_run(self):
            return ConferenceRegistrationTemporaryToken.objects.filter(expires__lt=timezone.now() - timedelta(minutes=30)).exists()

    @transaction.atomic
    def handle(self, *args, **options):
        ConferenceRegistrationTemporaryToken.objects.filter(expires__lt=timezone.now() - timedelta(minutes=30)).delete()
