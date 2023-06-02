#
# Run cleanup maintenance for all providers
#
# Copyright (C)2023, PostgreSQL Europe
#


from django.core.management.base import BaseCommand
from django.db import transaction

from datetime import time

from postgresqleu.digisign.models import DigisignProvider


class Command(BaseCommand):
    help = 'Run cleanup commands for all digisign providers'

    class ScheduledJob:
        scheduled_times = [time(3, 7), ]

        @classmethod
        def should_run(self):
            return DigisignProvider.objects.filter(active=True).exists()

    def handle(self, *args, **options):
        for provider in DigisignProvider.objects.filter(active=True):
            with transaction.atomic():
                provider.get_implementation().cleanup()
