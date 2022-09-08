# Message sending functionality lives in a separate module so it
# can easily be used both from a scheduled job and from a daemone
# when available.
from django.utils import timezone
from django.db import transaction

from datetime import timedelta
import time
import sys

from postgresqleu.confreg.models import NotificationQueue
from postgresqleu.confreg.models import ConferenceTweetQueue, ConferenceIncomingTweet
from postgresqleu.util.messaging.util import truncate_shortened_post


def send_pending_messages(providers):
    err = False

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
            try:
                if n.reg:
                    impl.send_direct_message(n.reg.messaging_config, n.msg)
                else:
                    impl.post_channel_message(n.messaging, n.channel, n.msg)
            except Exception as e:
                print("Failed to send notification to {} using {}: {}. Will retry until {}.".format(
                    n.reg and n.reg or n.channel,
                    n.messaging.provider.internalname,
                    e, n.expires
                ))
                err = True

                # Retry in 5 minutes
                n.time += timedelta(minutes=5)
                n.save()
            else:
                # Successfully posted, so delete it
                n.delete()

            # Rate limit us to one per second, that should usually be enough
            if first:
                first = False
            else:
                time.sleep(1)

    return not err


def send_pending_posts(providers):
    err = False

    numposts = 0
    for t in ConferenceTweetQueue.objects.prefetch_related('remainingtosend').filter(approved=True, sent=False, datetime__lte=timezone.now()).order_by('datetime'):
        sentany = False
        for p in t.remainingtosend.all():
            impl = providers.get(p)
            (id, err) = impl.post(
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
                sys.stderr.write("Failed to post to {}: {}".format(p, err))
                err = True
        if sentany:
            numposts += 1
            if not t.remainingtosend.exists():
                t.sent = True
            t.save(update_fields=['postids', 'sent'])

    numreposts = 0
    for t in ConferenceIncomingTweet.objects.select_related('provider').filter(retweetstate=1):
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

    return not err, numposts, numreposts
