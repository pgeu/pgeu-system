# This script does nightly batch runs for the membership system. Primarily,
# this means expiring old members, and notifying members that their
# membership is about to expire.
#
# First reminder is sent 30 days before expiry, then 20, then 10.
#
# Copyright (C) 2010-2013, PostgreSQL Europe
#
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.template import Context
from django.template.loader import get_template
from django.conf import settings

from datetime import datetime, timedelta

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.membership.models import Member, MemberLog

class Command(BaseCommand):
	help = 'Expire members and other nightly tasks'

	@transaction.atomic
	def handle(self, *args, **options):
		# Expire members (and let them know it happened)
		expired = Member.objects.filter(paiduntil__lt=datetime.now())
		for m in expired:
			MemberLog(member=m, timestamp=datetime.now(), message='Membership expired').save()
			# Generate an email to the user
			txt = get_template('membership/mail/expired.txt').render(Context({
						'member': m,
						}))
			send_simple_mail(settings.MEMBERSHIP_SENDER_EMAIL,
							 m.user.email,
							 "Your " + settings.ORG_NAME + " membership has expired",
							 txt)
			self.stdout.write(u"Expired member {0} (paid until {1})".format(m, m.paiduntil))
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
			txt = get_template('membership/mail/warning.txt').render(Context({
						'member': m,
						}))
			send_simple_mail(settings.MEMBERSHIP_SENDER_EMAIL,
							 m.user.email,
							 "Your " + settings.ORG_NAME + " membership will expire soon",
							 txt)
			self.stdout.write(u"Sent warning to member {0} (paid until {1}, last warned {2})".format(m, m.paiduntil, m.expiry_warning_sent))
			m.expiry_warning_sent = datetime.now()
			m.save()
