#
# Daemon to post all queued up notifications and social media posts
#

from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import autoreload

import sys
import threading
import select

from postgresqleu.util.messaging.sender import send_pending_messages, send_pending_posts
from postgresqleu.util.messaging import ProviderCache


class Command(BaseCommand):
    help = 'Daemon to post notification and social media posts'

    def handle(self, *args, **options):
        # Automatically exit if our own code changes.
        # This is not based on a published API, so quite likely will fail
        # and need to be updated in a future version of django

        # Start our work in a background thread
        bthread = threading.Thread(target=self.inner_handle)
        bthread.setDaemon(True)
        bthread.start()

        reloader = autoreload.get_reloader()
        while not reloader.should_stop:
            reloader.run(bthread)

        self.stderr.write("Underlying code changed, exiting for a restart")
        sys.exit(0)

    def inner_handle(self):
        with connection.cursor() as curs:
            curs.execute("LISTEN pgeu_notification")
            curs.execute("LISTEN pgeu_broadcast")
            curs.execute("SET application_name = 'pgeu messages/media poster'")

        while True:
            providers = ProviderCache()

            send_pending_messages(providers)
            send_pending_posts(providers)

            self.eat_notifications()

            # Wake up to check if there is something to do every 5 minutes, just in case
            select.select([connection.connection], [], [], 5 * 60)

    def eat_notifications(self):
        connection.connection.poll()
        while connection.connection.notifies:
            connection.connection.notifies.pop()
