from postgresqleu.confreg.models import ConferenceRegistration
from postgresqleu.confreg.models import ConferenceIncomingTweet, ConferenceIncomingTweetMedia
from postgresqleu.confreg.models import ConferenceTweetQueue
from postgresqleu.confreg.util import reglog

from postgresqleu.util.messaging import re_token

from .util import send_reg_direct_message

#
# This file holds common functionality used in multiple implementations but internally
# in the "Messaging framework"
#


def register_messaging_config(dm, messaging):
    # Does it look like a token? If so, try to attach!
    for m in re_token.findall(dm.txt):
        try:
            reg = ConferenceRegistration.objects.get(regtoken=m)
            # Matched reg, so set it up
            reg.messaging_config = messaging.get_regconfig_from_dm(dm)
            reg.save(update_fields=['messaging_config'])

            send_reg_direct_message(reg, 'Hello! This account is now configured to receive notifications for {}'.format(reg.conference))

            reglog(reg, "Connected to messaging account on {}: {}".format(
                messaging.typename,
                messaging.get_regdisplayname_from_config(reg.messaging_config),
            ))

            # This will be saved by the caller
            dm.internallyprocessed = True
            return True
        except ConferenceRegistration.DoesNotExist:
            pass
    return False


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
