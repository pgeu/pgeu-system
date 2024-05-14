# Send queued sponsor emails.
#

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.conf import settings

from datetime import timedelta

from postgresqleu.confsponsor.models import Sponsor, SponsorMail
from postgresqleu.confsponsor.util import send_conference_sponsor_notification, send_sponsor_manager_email
from postgresqleu.confreg.util import send_conference_mail


class Command(BaseCommand):
    help = 'Send sponsor emails'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=5)
        internal = True

        @classmethod
        def should_run(self):
            return SponsorMail.objects.filter(sentat__lte=timezone.now(), sent=False).exists()

    @transaction.atomic
    def handle(self, *args, **options):
        for msg in SponsorMail.objects.filter(sentat__lte=timezone.now(), sent=False):
            if msg.levels.exists():
                sponsors = list(Sponsor.objects.select_related('conference').filter(level__sponsormail=msg, confirmed=True))
                deststr = "sponsorship levels {}".format(", ".join(level.levelname for level in msg.levels.all()))
            else:
                sponsors = list(Sponsor.objects.select_related('conference').filter(sponsormail=msg))  # We include unconfirmed sponsors here intentionally!
                deststr = "sponsors {}".format(", ".join(s.name for s in sponsors))

            conference = None
            for sponsor in sponsors:
                conference = sponsor.conference
                send_sponsor_manager_email(
                    sponsor,
                    msg.subject,
                    'confsponsor/mail/sponsor_mail.txt',
                    {
                        'body': msg.message,
                        'sponsor': sponsor,
                    },
                )

                # And possibly send it out to the extra address for the sponsor
                if sponsor.extra_cc:
                    send_conference_mail(conference,
                                         sponsor.extra_cc,
                                         msg.subject,
                                         'confsponsor/mail/sponsor_mail.txt',
                                         {
                                             'body': msg.message,
                                             'sponsor': sponsor,
                                         },
                                         sender=conference.sponsoraddr,
                    )
            msg.sent = True
            msg.save(update_fields=['sent'])

            if conference:
                send_conference_sponsor_notification(
                    conference,
                    "Email sent to sponsors",
                    """An email was sent to sponsors of {0}
    with subject '{1}'.

    It was sent to {2}.

    ------
    {3}
    ------

    To view it on the site, go to {4}/events/sponsor/admin/{5}/viewmail/{6}/""".format(
                        conference,
                        msg.subject,
                        deststr,
                        msg.message,
                        settings.SITEBASE,
                        conference.urlname,
                        msg.id,
                    ),
                )
