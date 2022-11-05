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
from postgresqleu.confreg.models import NotificationQueue


class Command(BaseCommand):
    help = 'Send pending notifications'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=10)

        @classmethod
        def should_run(self):
            return NotificationQueue.objects.filter(time__lte=timezone.now()).exists()

    def handle(self, *args, **options):
        curs = connection.cursor()
        curs.execute("SELECT pg_try_advisory_lock(931779)")
        if not curs.fetchall()[0][0]:
            raise CommandError("Failed to get advisory lock, existing send_notifications process stuck?")

        providers = ProviderCache()

        ok, numsent = send_pending_messages(providers)
        if numsent:
            print("Sent {} notification messages".format(numsent))

        if not ok:
            sys.exit(1)
