# Message sending functionality lives in a separate module so it
# can easily be used both from a scheduled job and from a daemone
# when available.
from django.utils import timezone
from django.db import transaction

from datetime import timedelta
import requests
import time
import sys

from postgresqleu.confreg.models import NotificationQueue
from postgresqleu.confreg.models import ConferenceTweetQueue, ConferenceIncomingTweet
from postgresqleu.util.messaging.util import truncate_shortened_post


def send_pending_messages(providers):
    err = False
    numsent = 0

    # First delete any expired messages
    NotificationQueue.objects.filter(expires__lte=timezone.now()).delete()

    # Then one by one send off the ones that we have in the queue
    first = True
    while True:
        with transaction.atomic():
            msglist = list(NotificationQueue.objects.
                           select_for_update(of=('self',)).
                           select_related('reg', 'messaging', 'messaging__provider').
                           only('msg', 'channel', 'reg__messaging_config',
                                'messaging__config', 'reg__messaging__provider',
                           ).filter(time__lte=timezone.now()).
                           order_by('time', 'id')[:1])
            if len(msglist) == 0:
                break
            n = msglist[0]

            # Actually Send Message (TM)
            impl = providers.get(n.messaging.provider)
            thiserr = False
            try:
                if n.reg:
                    # If the user is part way through registering their messaging provider we will have a
                    # messaging set, but messaging_config will be an empty dict.
                    if n.reg.messaging_config != {}:
                        impl.send_direct_message(n.reg.messaging_config, n.msg)
                else:
                    impl.post_channel_message(n.messaging, n.channel, n.msg)
            except requests.exceptions.HTTPError as re:
                # Special-case http errors coming out of requests, if we have any.
                thiserr = True
                sys.stderr.write("Failed to send notification to {} using {}: HTTP error {}. Will retry until {}.\n".format(
                    n.reg and n.reg or n.channel,
                    n.messaging.provider.internalname,
                    e, n.expires
                ))
                if re.response.text:
                    sys.stderr.write("Response text: {}\n".format(re.response.text))
            except Exception as e:
                thiserr = True
                sys.stderr.write("Failed to send notification to {} using {}: {}. Will retry until {}.\n".format(
                    n.reg and n.reg or n.channel,
                    n.messaging.provider.internalname,
                    e, n.expires
                ))

            # Common path for all errors
            if thiserr:
                err = True

                # Retry in 5 minutes
                n.time += timedelta(minutes=5)
                n.save(update_fields=['time'])
            else:
                # Successfully posted, so delete it
                n.delete()
                numsent += 1

            # Rate limit us to one per second, that should usually be enough
            if first:
                first = False
            else:
                time.sleep(1)

    return not err, numsent


def send_pending_posts(providers):
    errpost, numposts = _send_pending_posts(providers)
    errrepost, numreposts = _send_pending_reposts(providers)

    return not (errpost or errrepost), numposts, numreposts


def _send_pending_posts(providers):
    err = False
    numposts = 0
    while True:
        with transaction.atomic():
            tlist = list(ConferenceTweetQueue.objects.
                         select_for_update(of=('self', )).
                         filter(approved=True, sent=False, datetime__lte=timezone.now()).
                         order_by('datetime')[:1])
            if len(tlist) == 0:
                break
            t = tlist[0]
            sentany = False
            remaining = list(t.remainingtosend.select_for_update().all())
            if not remaining:
                # Nothing remaining for this tweet, so flag it as done. Normally this shouldn't happen,'
                # but it can happen if news is posted prior to the twitter account being enabled.
                t.sent = True
                t.save(update_fields=['sent', ])
                break

            for p in remaining:
                impl = providers.get(p)
                (id, errmsg) = impl.post(
                    truncate_shortened_post(t.contents, impl.max_post_length),
                    t.image,
                    t.replytotweetid,
                )

                if id:
                    t.remainingtosend.remove(p)
                    # postids is a map of <provider status id> -> <provider id>. It's mapped
                    # "backwards" this way because the main check we do is if a key exists.
                    t.postids[id] = p.id
                    sentany = True
                else:
                    sys.stderr.write("Failed to post to {}: {}\n".format(p, errmsg))
                    err = True
            if sentany:
                numposts += 1
                if not t.remainingtosend.exists():
                    t.sent = True
                t.save(update_fields=['postids', 'sent'])

        # Sleep 1 second before continuing so we don't hammer the APIs
        if err:
            # On error, we sleep a minute instead, so we don't completely flood things
            sys.stderr.write("One or more errors detected, sleeping 60 seconds before trying again.\n")
            time.sleep(60)
        else:
            time.sleep(1)
    return err, numposts


def _send_pending_reposts(providers):
    err = False
    numreposts = 0
    while True:
        with transaction.atomic():
            tlist = list(ConferenceIncomingTweet.objects.
                         select_for_update(of=('self', )).
                         select_related('provider').
                         filter(retweetstate=1)[:1])
            if len(tlist) == 0:
                break
            t = tlist[0]

            # These are tweets that should be retweeted. Retweets only happen on the same
            # provider that they were posted on.
            impl = providers.get(t.provider)

            ok, msg = impl.repost(t.statusid)
            if ok:
                t.retweetstate = 2
                t.save(update_fields=['retweetstate'])
                numreposts += 1
            else:
                sys.stderr.write("Failed to repost on {}: {}\n".format(t.provider, msg))
                err = True

        # Sleep 1 second before continuing so we don't hammer the APIs
        time.sleep(1)

    return err, numreposts
