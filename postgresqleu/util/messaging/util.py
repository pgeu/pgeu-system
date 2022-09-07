from django.utils import timezone

from datetime import timedelta
import re

from postgresqleu.confreg.models import NotificationQueue
from postgresqleu.confreg.models import ConferenceIncomingTweet, ConferenceIncomingTweetMedia
from postgresqleu.confreg.models import ConferenceTweetQueue
from postgresqleu.util.db import exec_no_result
from postgresqleu.util.messaging import get_messaging_class


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


def store_incoming_post(provider, post):
    # Have we already seen this post?
    if ConferenceIncomingTweet.objects.filter(provider=provider, statusid=post['id']).exists():
        return False

    # Is this one of our own outgoing posts?
    if ConferenceTweetQueue.objects.filter(postids__contains={post['id']: provider.id}).exists():
        return False

    i = ConferenceIncomingTweet(
        conference=provider.route_incoming,
        provider=provider,
        statusid=post['id'],
        created=post['datetime'],
        text=post['text'],
        replyto_statusid=post['replytoid'],
        author_name=post['author']['name'],
        author_screenname=post['author']['username'],
        author_id=post['author']['id'],
        author_image_url=post['author']['imageurl'],
    )
    if post.get('quoted', None):
        i.quoted_statusid = post['quoted']['id']
        i.quoted_text = post['quoted']['text']
        i.quoted_permalink = post['quoted']['permalink']
    i.save()
    for seq, m in enumerate(post['media']):
        ConferenceIncomingTweetMedia(incomingtweet=i,
                                     sequence=seq,
                                     mediaurl=m).save()

    return True


# This does not appear to match everything in any shape or form, but we are only
# using it against URLs that we have typed in ourselves, so it should be easy
# enough.
# Should be in sync with regexp in js/admin.js
_re_urlmatcher = re.compile(r'\bhttps?://\S+', re.I)

# This is currently the value for Twitter and the default for Mastodon, so just
# use that globally for now.
_url_shortened_len = 23
_url_counts_as_characters = "https://short.url/{}".format((_url_shortened_len - len("https://short.url/")) * 'x')


def get_shortened_post_length(txt):
    return len(_re_urlmatcher.sub(_url_counts_as_characters, txt))


# Truncate a text, taking into account URL shorterners. WIll not truncate in the middle of an URL,
# but right now will happily truncate in the middle of a word (room for improvement!)
def truncate_shortened_post(txt, maxlen):
    matches = list(_re_urlmatcher.finditer(txt))

    if not matches:
        # Not a single url, so just truncate
        return txt[:maxlen]

    firststart, firstend = matches[0].span()
    if firststart + _url_shortened_len > maxlen:
        # We hit the size limit before the url or in the middle of it, so skip the whole url
        return txt[:firststart]

    inlen = firstend
    outlen = firststart + _url_shortened_len
    for i, curr in enumerate(matches[1:]):
        prevstart, prevend = matches[i].span()
        currstart, currend = curr.span()

        betweenlen = currstart - prevend
        if outlen + betweenlen > maxlen:
            # The limit was hit in the text between urls
            left = maxlen - outlen
            return txt[:inlen + (maxlen - outlen)]
        if outlen + betweenlen + _url_shortened_len > maxlen:
            # The limit was hit in the middle of this URL, so include all the text
            # up to it, but skip the url.
            return txt[:inlen + betweenlen]

        # The whole URL fit
        inlen += betweenlen + currend - currstart
        outlen += betweenlen + _url_shortened_len

    return txt[:inlen + (maxlen - outlen)]
