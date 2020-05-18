#
# Script to send outgoing notifications
#


from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import connection

from datetime import timedelta
import sys

from postgresqleu.util.messaging import ProviderCache
from postgresqleu.util.messaging.sender import send_pending_messages


class Command(BaseCommand):
    help = 'Send pending notifications'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=10)

        @classmethod
        def should_run(self):
            return Notification.objects.filter(time__lte=timezone.now()).exists()

    def handle(self, *args, **options):
        curs = connection.cursor()
        curs.execute("SELECT pg_try_advisory_lock(931779)")
        if not curs.fetchall()[0][0]:
            raise CommandError("Failed to get advisory lock, existing post_media_broadcasts process stuck?")

        providers = ProviderCache()

        if not send_pending_messages(providers):
            sys.exit(1)
