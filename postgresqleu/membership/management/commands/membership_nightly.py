# This script does nightly batch runs for the membership system. Primarily,
# this means expiring old members, and notifying members that their
# membership is about to expire.
#
# First reminder is sent 30 days before expiry, then 20, then 10.
#
# Copyright (C) 2010-2013, PostgreSQL Europe
#
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.conf import settings

from datetime import datetime, timedelta, time
from datetime import time

from postgresqleu.mailqueue.util import send_template_mail
from postgresqleu.membership.models import Member, MemberLog, get_config


class Command(BaseCommand):
    help = 'Expire members and other nightly tasks'

    class ScheduledJob:
        scheduled_times = [time(23, 50), ]
        internal = True

    @transaction.atomic
    def handle(self, *args, **options):
        cfg = get_config()

        # Expire members (and let them know it happened)
        expired = Member.objects.filter(paiduntil__lt=datetime.now())
        for m in expired:
            MemberLog(member=m, timestamp=datetime.now(), message='Membership expired').save()
            # Generate an email to the user
            send_template_mail(cfg.sender_email,
                               m.user.email,
                               "Your {0} membership has expired".format(settings.ORG_NAME),
                               'membership/mail/expired.txt',
                               {
                                   'member': m,
                               },
            )
            self.stdout.write("Expired member {0} (paid until {1})".format(m, m.paiduntil))
            # An expired member has no membersince and no paiduntil.
            m.membersince = None
            m.paiduntil = None
            m.save()

        # Send warnings to members about to expire. We explicitly avoid sending
        # a warning in the last 24 hours before expire, so we don't end up sending
        # both a warning and an expiry within minutes in case the cronjob runs on
        # slightly different times.

        warning = Member.objects.filter(
            Q(paiduntil__gt=datetime.now() - timedelta(days=1)) &
            Q(paiduntil__lt=datetime.now() + timedelta(days=30)) &
            (
                Q(expiry_warning_sent__lt=datetime.now() - timedelta(days=10)) |
                Q(expiry_warning_sent__isnull=True)
                ))
        for m in warning:
            MemberLog(member=m, timestamp=datetime.now(), message='Membership expiry warning sent to %s' % m.user.email).save()
            # Generate an email to the user
            send_template_mail(cfg.sender_email,
                               m.user.email,
                               "Your {0} membership will expire soon".format(settings.ORG_NAME),
                               'membership/mail/warning.txt',
                               {
                                   'member': m,
                               },
                           )
            self.stdout.write("Sent warning to member {0} (paid until {1}, last warned {2})".format(m, m.paiduntil, m.expiry_warning_sent))
            m.expiry_warning_sent = datetime.now()
            m.save()
