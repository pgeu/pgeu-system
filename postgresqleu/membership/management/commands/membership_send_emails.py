# Send queued attendee emails.
#

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from datetime import timedelta

from postgresqleu.membership.models import MemberMail, get_config
from postgresqleu.confreg.jinjafunc import render_sandboxed_template
from postgresqleu.mailqueue.util import send_template_mail


class Command(BaseCommand):
    help = 'Send membership emails'

    class ScheduledJob:
        scheduled_interval = timedelta(minutes=30)
        internal = True

        @classmethod
        def should_run(self):
            return MemberMail.objects.filter(sentat__lte=timezone.now(), sent=False).exists()

    @transaction.atomic
    def handle(self, *args, **options):
        cfg = get_config()

        for msg in MemberMail.objects.prefetch_related('sentto', 'sentto__user').filter(sentat__lte=timezone.now(), sent=False):
            for member in msg.sentto.all():
                send_template_mail(
                    cfg.sender_email,
                    member.user.email,
                    msg.subject,
                    'membership/mail/member_mail.txt',
                    {
                        'subject': msg.subject,
                        'body': render_sandboxed_template(msg.message, {
                            'member': member,
                        }),
                    },
                    sendername=cfg.sender_name,
                    receivername=member.fullname,
                )
            msg.sent = True
            msg.save(update_fields=['sent'])
