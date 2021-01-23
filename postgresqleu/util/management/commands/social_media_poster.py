#
# Daemon to post all queued up notifications and social media posts
#

from django.db import connection

import select

from postgresqleu.util.reload import ReloadCommand
from postgresqleu.util.messaging.sender import send_pending_messages, send_pending_posts
from postgresqleu.util.messaging import ProviderCache


class Command(ReloadCommand):
    help = 'Daemon to post notification and social media posts'

    def handle_with_reload(self, *args, **options):
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
