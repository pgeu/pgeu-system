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
from postgresqleu.confreg.models import ConferenceTweetQueueErrorLog
from postgresqleu.util.messaging.short import truncate_shortened_post


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
                    re, n.expires
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
            # Get all pending tweets to post. If a tweet has errors on it, it get postponed by
            # the very unscientific formula of 2.25^(errorcount+4) up to 10 attempts, which means
            # the first retry is after ~ 1 minute and the last one after ~24 hours.
            tlist = list(ConferenceTweetQueue.objects.raw("""SELECT * FROM confreg_conferencetweetqueue
WHERE approved AND NOT sent AND
  datetime + CASE WHEN errorcount>0 THEN pow(2.25, errorcount+4) * '1 second'::interval ELSE '0' END  <= CURRENT_TIMESTAMP
ORDER BY datetime
LIMIT 1
FOR UPDATE OF confreg_conferencetweetqueue"""))

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
                contents = t.contents[str(p.id)] if isinstance(t.contents, dict) else t.contents
                # Don't try to post it if it's empty
                if contents:
                    (id, errmsg) = impl.post(
                        truncate_shortened_post(
                            contents,
                            impl.max_post_length
                        ),
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
                        ConferenceTweetQueueErrorLog(tweet=t, message="Failed to post to {}: {}".format(p, errmsg)[:250]).save()
                        err = True
                else:
                    sys.stderr.write("Not making empty post to {}\n".format(p))
                    ConferenceTweetQueueErrorLog(tweet=t, message="Not making empty post to {}".format(p))
                    t.remainingtosend.remove(p)
                    sentany = True
            if sentany:
                numposts += 1
                if not t.remainingtosend.exists():
                    t.sent = True
                t.save(update_fields=['postids', 'sent'])

            if err:
                # On error, postpone the next try so we don't get stuck in a loop
                t.errorcount += 1
                if t.errorcount > 10:
                    # After 10 attempts we give up - and flag it as sent
                    t.sent = True
                    t.save(update_fields=['errorcount', 'sent'])
                    ConferenceTweetQueueErrorLog(tweet=t, message='Too many failures, giving up on this posting and flagging as sent.').save()
                else:
                    t.save(update_fields=['errorcount'])

        # Sleep 1 second before continuing so we don't hammer the APIs
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
