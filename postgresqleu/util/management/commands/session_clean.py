# Clean old sessions
#
# Copyright (C) 2019, PostgreSQL Europe
#
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from datetime import timedelta


class Command(BaseCommand):
    help = 'Expire old django sessions'

    class ScheduledJob:
        scheduled_interval = timedelta(hours=3)
        internal = True

    def handle(self, *args, **kwargs):
        with connection.cursor() as curs:
            curs.execute("WITH d AS (DELETE FROM django_session WHERE expire_date < now() - '1 week'::interval RETURNING expire_date) SELECT COUNT(*) FROM d")
            n, = curs.fetchone()
            if n:
                self.stdout.write("Expired {} sessions.\n".format(n))
            else:
                self.stdout.write("Nothing done, sorry\n")
