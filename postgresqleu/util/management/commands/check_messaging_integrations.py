#
# Script to (optionally) validate all messaging integrations
#
# This can include for example checking that webhooks are still existing,
# and marked as valid. Actual implementation depends on the messaging provider.
#


from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

import datetime
import io
import sys
from collections import defaultdict

from postgresqleu.util.messaging import get_messaging

from postgresqleu.confreg.models import MessagingProvider


class Command(BaseCommand):
    help = 'Validate messaging integrations'

    class ScheduledJob:
        scheduled_time = datetime.time(4, 19)
        default_notify_on_success = True

        @classmethod
        def should_run(self):
            return MessagingProvider.objects.filter(active=True).exists()

    def handle(self, *args, **options):
        s = io.StringIO()
        err = False

        state = defaultdict(dict)
        for provider in MessagingProvider.objects.filter(active=True).order_by('classname'):
            impl = get_messaging(provider)

            try:
                result, out = impl.check_messaging_config(state[provider.classname])
            except Exception as e:
                result = False
                out = "EXCEPTION: {}\n".format(e)

            if out:
                s.write("{}\n".format(provider.internalname))
                s.write("{}\n".format('-' * len(provider.internalname)))
                s.write(out)
                s.write("\n\n")
            if not result:
                err = True

        if s.tell() != 0:
            print(s.getvalue())

        if err:
            sys.exit(1)
