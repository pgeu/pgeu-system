# Script to send off all queued email.
#
# This script is intended to be run frequently from cron. We queue things
# up in the db so that they get automatically rolled back as necessary,
# but once we reach this point we're just going to send all of them one
# by one.
#
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

import smtplib

from postgresqleu.mailqueue.models import QueuedMail

class Command(BaseCommand):
    help = 'Send queued mail'

    def handle(self, *args, **options):
        # Grab advisory lock, if available. Lock id is just a random number
        # since we only need to interlock against ourselves. The lock is
        # automatically released when we're done.
        curs = connection.cursor()
        curs.execute("SELECT pg_try_advisory_lock(72181378)")
        if not curs.fetchall()[0][0]:
            raise CommandError("Failed to get advisory lock, existing send_queued_mail process stuck?")

        for m in QueuedMail.objects.all():
            # Yes, we do a new connection for each run. Just because we can.
            # If it fails we'll throw an exception and just come back on the
            # next cron job. And local delivery should never fail...
            smtp = smtplib.SMTP("localhost")
            smtp.sendmail(m.sender, m.receiver, m.fullmsg.encode('utf-8'))
            smtp.close()
            m.delete()
