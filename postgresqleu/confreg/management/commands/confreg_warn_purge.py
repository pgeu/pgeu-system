#
# Send warnings when a conference has not purged their personal
# data long after the conference ended.
#
# Intended to run on a weekly basis or so, as it will keep repeating
# the reminders every time.
#
from django.core.management.base import BaseCommand
from django.conf import settings

from datetime import datetime, timedelta

from postgresqleu.mailqueue.util import send_simple_mail

from postgresqleu.confreg.models import Conference

class Command(BaseCommand):
    help = 'Send warnings about purging personal data'

    def handle(self, *args, **options):
        for conference in Conference.objects.filter(personal_data_purged__isnull=True,
                                                    enddate__lt=datetime.now() - timedelta(days=30)) \
                                                    .extra(where=["EXISTS (SELECT 1 FROM confreg_conferenceregistration r WHERE r.conference_id=confreg_conference.id)"]):
            send_simple_mail(conference.contactaddr,
                             conference.contactaddr,
                             u"{0}: time to purge personal data?".format(conference.conferencename),
                             u"""Conference {0} finished on {1},
but personal data has not been purged.

In accordance with the rules, personal data should be purged
as soon as it's no longer needed. So please consider doing so,
from the conference dashboard:

{2}/events/admin/{3}/
""".format(conference.conferencename, conference.enddate, settings.SITEBASE, conference.urlname),
                             sendername = conference.conferencename,
                             receivername = conference.conferencename,
                             bcc = settings.ADMINS[0][1],
            )

