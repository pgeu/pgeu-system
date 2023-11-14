#
# Fetch completed contracts from digisign providers
#
# Copyright (C)2023, PostgreSQL Europe
#


from django.core.management.base import BaseCommand
from django.db import transaction

from datetime import time

from postgresqleu.digisign.models import DigisignProvider, DigisignDocument


class Command(BaseCommand):
    help = 'Fetch completed contracts for all digisign providers'

    class ScheduledJob:
        scheduled_times = [time(1, 1), ]

        @classmethod
        def should_run(self):
            return DigisignDocument.objects.filter(provider__active=True, completed__isnull=False, digisigncompleteddocument__isnull=True).exists()

    def handle(self, *args, **options):
        error = False
        for provider in DigisignProvider.objects.filter(active=True):
            impl = provider.get_implementation()
            for doc in DigisignDocument.objects.filter(provider=provider, completed__isnull=False, digisigncompleteddocument__isnull=True):
                try:
                    with transaction.atomic():
                        provider.get_implementation().fetch_completed(doc)
                except Exception as e:
                    self.stderr.write("Failed to download completed document {}: {}\n".format(doc.documentid, e))
                    error = True
        if error:
            raise Exception("Failed to download one or more documents")
