#
# Script to (optionally) validate all messaging integrations
#
# This can include for example checking that webhooks are still existing,
# and marked as valid. Actual implementation depends on the messaging provider.
#


from django.core.management.base import BaseCommand

import datetime
import io
import sys
from collections import defaultdict

from postgresqleu.util.messaging import get_messaging

from postgresqleu.confreg.models import MessagingProvider
from postgresqleu.confreg.util import send_conference_notification


class Command(BaseCommand):
    help = 'Validate messaging integrations and refresh tokens'

    class ScheduledJob:
        scheduled_times = [datetime.time(4, 19)]
        default_notify_on_success = True

        @classmethod
        def should_run(self):
            return MessagingProvider.objects.filter(active=True).exists()

    def handle(self, *args, **options):
        s = io.StringIO()
        err = False

        state = defaultdict(dict)
        out_by_series = defaultdict(str)

        for provider in MessagingProvider.objects.select_related('series').filter(active=True).order_by('classname'):
            impl = get_messaging(provider)
            try:
                result, out = impl.check_messaging_config(state[provider.classname])
                if not result and provider.series:
                    out_by_series[provider.series] += "{}: {}\n".format(provider, out)
            except Exception as e:
                result = False
                out = "EXCEPTION: {}\n".format(e)

            if out:
                s.write("{} (for {})\n".format(provider.internalname, provider.series.name if provider.series else 'News'))
                s.write("{}\n".format('-' * len(provider.internalname)))
                s.write(out)
                s.write("\n\n")
            if not result:
                err = True

        if s.tell() != 0:
            print(s.getvalue())

        for k, v in out_by_series.items():
            # Send a notification to the conference that's the latest in the series
            send_conference_notification(
                k.conference_set.order_by('-startdate')[0],
                'Messaging provider issues',
                "The following messaging provider issues have been recorded for the series {}\n\n{}\n".format(
                    k.name,
                    v,
                ),
            )

        if err:
            sys.exit(1)
