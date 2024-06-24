#
# Script to fetch incoming direct messages
#


from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Q

from datetime import timedelta, datetime
import sys

from postgresqleu.util.messaging import get_messaging

from postgresqleu.confreg.models import MessagingProvider


class Command(BaseCommand):
    help = 'Fetch direct messages'

    class ScheduledJob:
        # Normally this integreates with webhooks, so we run the catchup
        # part separately and infrequently.
        scheduled_interval = timedelta(minutes=15)

        @classmethod
        def should_run(self):
            return MessagingProvider.objects.filter(Q(conferencemessaging__privatebcast=True) | Q(conferencemessaging__notification=True) | Q(conferencemessaging__orgnotification=True), active=True, series__isnull=False)

    def handle(self, *args, **options):
        curs = connection.cursor()
        curs.execute("SELECT pg_try_advisory_lock(983231)")
        if not curs.fetchall()[0][0]:
            raise CommandError("Failed to get advisory lock, existing fetch_direct_messages process stuck?")

        err = False

        for provider in MessagingProvider.objects.raw("SELECT * FROM confreg_messagingprovider mp WHERE active AND series_id IS NOT NULL AND EXISTS (SELECT 1 FROM confreg_conferencemessaging m WHERE m.provider_id=mp.id AND (m.privatebcast OR m.notification OR m.orgnotification))"):
            impl = get_messaging(provider)

            try:
                with transaction.atomic():
                    (lastpoll, checkpoint) = impl.poll_incoming_private_messages(provider.private_lastpoll, provider.private_checkpoint)
                    provider.private_lastpoll = lastpoll
                    provider.private_checkpoint = checkpoint
                    provider.save(update_fields=['private_lastpoll', 'private_checkpoint'])
            except Exception as e:
                print("{}: Failed to poll {} for direct messages: {}".format(str(datetime.now()), provider, e))
                err = True

        if err:
            # Error message printed earlier, but we need to exit with non-zero exitcode
            # to flag the whole job as failed.
            sys.exit(1)
