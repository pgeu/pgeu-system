from django.utils import timezone

from datetime import timedelta

from postgresqleu.confreg.models import NotificationQueue
from postgresqleu.util.db import exec_no_result
from postgresqleu.util.messaging import get_messaging_class

#
# This file holds methods callable from outside the "messaging framework"
#


class _Notifier(object):
    def __enter__(self):
        self.notified = False
        return self

    def notify(self):
        self.notified = True

    def __exit__(self, *args):
        if self.notified:
            exec_no_result('NOTIFY pgeu_notification')


def send_reg_direct_message(reg, msg, expiry=timedelta(hours=1)):
    with _Notifier() as n:
        if reg.messaging and reg.messaging.provider.active:
            NotificationQueue(
                time=timezone.now(),
                expires=timezone.now() + expiry,
                messaging=reg.messaging,
                reg=reg,
                channel=None,
                msg=msg,
            ).save()
            n.notify()


def send_private_broadcast(conference, msg, expiry=timedelta(hours=1)):
    with _Notifier() as n:
        for messaging in conference.conferencemessaging_set.filter(privatebcast=True, provider__active=True):
            NotificationQueue(
                time=timezone.now(),
                expires=timezone.now() + expiry,
                messaging=messaging,
                reg=None,
                channel="privatebcast",
                msg=msg,
            ).save()
            n.notify()


def send_org_notification(conference, msg, expiry=timedelta(hours=1)):
    with _Notifier() as n:
        for messaging in conference.conferencemessaging_set.filter(orgnotification=True, provider__active=True):
            NotificationQueue(
                time=timezone.now(),
                expires=timezone.now() + expiry,
                messaging=messaging,
                reg=None,
                channel="orgnotification",
                msg=msg,
            ).save()
            n.notify()


def send_channel_message(messaging, channel, msg, expiry=timedelta(hours=1)):
    with _Notifier() as n:
        NotificationQueue(
            time=timezone.now(),
            expires=timezone.now() + expiry,
            messaging=messaging,
            reg=None,
            channel=channel,
            msg=msg,
        ).save()
        n.notify()


def notify_twitter_moderation(tweet, completed, approved):
    for messaging in tweet.conference.conferencemessaging_set.filter(socialmediamanagement=True, provider__active=True):
        get_messaging_class(messaging.provider.classname)(messaging.provider.id, messaging.provider.config).notify_twitter_moderation(messaging, tweet, completed, approved)
