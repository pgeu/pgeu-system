from django.core.serializers.json import DjangoJSONEncoder
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import transaction
from django.utils import timezone

import datetime
import io
import json
from PIL import Image, ImageFile

from postgresqleu.scheduler.util import trigger_immediate_job_run
from postgresqleu.util.request import get_int_or_error
from postgresqleu.util.messaging import ProviderCache
from .models import ConferenceTweetQueue, ConferenceIncomingTweet, ConferenceMessaging
from .models import Conference, ConferenceRegistration


def post_conference_social(conference, contents, approved=False, posttime=None, author=None):
    if not posttime:
        posttime = timezone.now()

    localtime = timezone.localtime(posttime, conference.tzobj)
    localtimeonly = localtime.time()

    # Adjust the start time to be inside the configured window
    if localtimeonly < conference.twitter_timewindow_start:
        # Trying to post before the first allowed time, so just adjust it forward until we
        # get to the allowed time.
        posttime = timezone.make_aware(
            datetime.datetime.combine(localtime, conference.twitter_timewindow_start),
            conference.tzobj,
        )
    elif localtimeonly > conference.twitter_timewindow_end:
        # Trying to post after the last allowed time, so adjust it forward until the first
        # allowed time *the next day*
        posttime = timezone.make_aware(
            datetime.datetime.combine(posttime + datetime.timedelta(days=1), conference.twitter_timewindow_start),
            conference.tzobj,
        )

    t = ConferenceTweetQueue(conference=conference,
                             contents=contents[:1000],
                             approved=approved,
                             datetime=posttime,
                             author=author)
    t.save()
    return t


def _json_response(d):
    return HttpResponse(json.dumps(d, cls=DjangoJSONEncoder), content_type='application/json')


@csrf_exempt
@transaction.atomic
def volunteer_twitter(request, urlname, token):
    try:
        conference = Conference.objects.select_related('series').get(urlname=urlname)
    except Conference.DoesNotExist:
        raise Http404()

    if not conference.has_social_broadcast:
        raise Http404()

    reg = get_object_or_404(ConferenceRegistration, conference=conference, regtoken=token)
    if conference.administrators.filter(pk=reg.attendee_id).exists() or conference.series.administrators.filter(pk=reg.attendee_id):
        is_admin = True
        canpost = conference.twitter_postpolicy != 0
        canpostdirect = conference.twitter_postpolicy != 0
        canmoderate = conference.twitter_postpolicy in (2, 3)
    elif not conference.volunteers.filter(pk=reg.pk).exists():
        raise Http404()
    else:
        is_admin = False
        canpost = conference.twitter_postpolicy >= 2
        canpostdirect = conference.twitter_postpolicy == 4
        canmoderate = conference.twitter_postpolicy == 3

    providers = ProviderCache()

    if request.method == 'POST':
        if request.POST.get('op', '') == 'post':
            approved = False
            approvedby = None
            if is_admin:
                if conference.twitter_postpolicy == 0:
                    raise PermissionDenied()

                # Admins can use the bypass parameter to, well, bypass
                if request.POST.get('bypass', '0') == '1':
                    approved = True
                    approvedby = reg.attendee
            else:
                if conference.twitter_postpolicy in (0, 1):
                    raise PermissionDenied()

                if conference.twitter_postpolicy == 4:
                    # Post without approval for volunteers
                    approved = True
                    approvedby = reg.attendee

            # Check if we have *exactly the same tweet* in the queue already, in the past 5 minutes.
            # in which case it's most likely a clicked-too-many-times.
            if ConferenceTweetQueue.objects.filter(conference=conference, contents=request.POST['txt'], author=reg.attendee, datetime__gt=timezone.now() - datetime.timedelta(minutes=5)):
                return _json_response({'error': 'Duplicate post detected'})

            # Now insert it in the queue, bypassing time validation since it's not an automatically
            # generated tweet.
            t = ConferenceTweetQueue(
                conference=conference,
                contents=request.POST['txt'][:280],
                approved=approved,
                approvedby=approvedby,
                author=reg.attendee,
                replytotweetid=request.POST.get('replyid', None),
                )
            if 'image' in request.FILES:
                t.image = request.FILES['image'].read()
                # Actually validate that it loads as PNG or JPG
                try:
                    p = ImageFile.Parser()
                    p.feed(t.image)
                    p.close()
                    image = p.image
                    if image.format not in ('PNG', 'JPEG'):
                        return _json_response({'error': 'Image must be PNG or JPEG, not {}'.format(image.format)})
                except Exception as e:
                    return _json_response({'error': 'Failed to parse image'})

                MAXIMAGESIZE = 1 * 1024 * 1024
                if len(t.image) > MAXIMAGESIZE:
                    # Image is bigger than 4Mb, but it is a valid image, so try to rescale it
                    # We can't know exactly how to resize it to get it to the right size, but most
                    # likely if we cut the resolution by n% the filesize goes down by > n% (usually
                    # an order of magnitude), so we base it on that and just fail again if that didn't
                    # work.
                    rescalefactor = MAXIMAGESIZE / len(t.image)
                    newimg = image.resize((int(image.size[0] * rescalefactor), int(image.size[1] * rescalefactor)), Image.ANTIALIAS)
                    b = io.BytesIO()
                    newimg.save(b, image.format)
                    t.image = b.getvalue()
                    if len(t.image) > MAXIMAGESIZE:
                        return _json_response({'error': 'Image file too big and automatic resize failed'})

            t.save()
            if request.POST.get('replyid', None):
                orig = ConferenceIncomingTweet.objects.select_related('provider').get(conference=conference, statusid=get_int_or_error(request.POST, 'replyid'))
                orig.processedat = timezone.now()
                orig.processedby = reg.attendee
                orig.save()
                # When when replying to a tweet, it goes to the original provider *only*
                t.remainingtosend.set([orig.provider])

            return _json_response({})
        elif request.POST.get('op', None) in ('approve', 'discard'):
            if not is_admin:
                # Admins can always approve, but volunteers only if policy allows
                if conference.twitter_postpolicy != 3:
                    raise PermissionDenied()

            try:
                t = ConferenceTweetQueue.objects.get(conference=conference, approved=False, pk=get_int_or_error(request.POST, 'id'))
            except ConferenceTweetQueue.DoesNotExist:
                return _json_response({'error': 'Tweet already discarded'})
            if t.approved:
                return _json_response({'error': 'Tweet has already been approved'})

            if request.POST.get('op') == 'approve':
                if t.author == reg.attendee:
                    return _json_response({'error': "Can't approve your own tweets"})

                t.approved = True
                t.approvedby = reg.attendee
                t.save()
                trigger_immediate_job_run('post_media_broadcasts')
            else:
                t.delete()
            return _json_response({})
        elif request.POST.get('op', None) in ('dismissincoming', 'retweet'):
            if not is_admin:
                # Admins can always approve, but volunteers only if policy allows
                if conference.twitter_postpolicy != 3:
                    raise PermissionDenied()

            try:
                t = ConferenceIncomingTweet.objects.get(conference=conference, statusid=get_int_or_error(request.POST, 'id'))
            except ConferenceIncomingTweet.DoesNotExist:
                return _json_response({'error': 'Tweet does not exist'})

            if request.POST.get('op', None) == 'dismissincoming':
                if t.processedat:
                    return _json_response({'error': 'Tweet is already dismissed or replied'})

                t.processedby = reg.attendee
                t.processedat = timezone.now()
                t.save(update_fields=['processedby', 'processedat'])
            else:
                if t.retweetstate > 0:
                    return _json_response({'error': 'Tweet '})
                t.retweetstate = 1
                t.save(update_fields=['retweetstate'])
                trigger_immediate_job_run('post_media_broadcasts')

            return _json_response({})
        else:
            # Unknown op
            raise Http404()

    # GET request here
    if request.GET.get('op', None) == 'queue':
        # We show the queue to everybody, but non-moderators don't get to approve

        # Return the approval queue
        queue = ConferenceTweetQueue.objects.defer('image', 'imagethumb').filter(conference=conference, approved=False).extra(
            select={'hasimage': "image is not null and image != ''"}
        ).order_by('datetime')

        # Return the latest ones approved
        latest = ConferenceTweetQueue.objects.defer('image', 'imagethumb').filter(conference=conference, approved=True).extra(
            select={'hasimage': "image is not null and image != ''"}
        ).order_by('-datetime')[:5]

        def _postdata(objs):
            return [
                {
                    'id': t.id,
                    'txt': t.contents,
                    'author': t.author and t.author.username or '',
                    'time': t.datetime,
                    'hasimage': t.hasimage,
                    'delivered': t.sent,
                }
                for t in objs]

        return _json_response({
            'queue': _postdata(queue),
            'latest': _postdata(latest),
        })
    elif request.GET.get('op', None) == 'incoming':
        incoming = ConferenceIncomingTweet.objects.select_related('provider').filter(conference=conference, processedat__isnull=True).order_by('created')
        latest = ConferenceIncomingTweet.objects.select_related('provider').filter(conference=conference, processedat__isnull=False).order_by('-processedat')[:5]

        def _postdata(objs):
            return [
                {
                    'id': str(t.statusid),
                    'txt': t.text,
                    'author': t.author_screenname,
                    'authorfullname': t.author_name,
                    'time': t.created,
                    'rt': t.retweetstate,
                    'provider': t.provider.publicname,
                    'media': [m for m in t.media if m is not None],
                    'url': providers.get(t.provider).get_public_url(t),
                    'replymaxlength': providers.get(t.provider).max_post_length,
                }
                for t in objs.annotate(media=ArrayAgg('conferenceincomingtweetmedia__mediaurl'))]
        return _json_response({
            'incoming': _postdata(incoming),
            'incominglatest': _postdata(latest),
        })
    elif request.GET.get('op', None) == 'hasqueue':
        return _json_response({
            'hasqueue': ConferenceTweetQueue.objects.filter(conference=conference, approved=False).exclude(author=reg.attendee_id).exists(),
            'hasincoming': ConferenceIncomingTweet.objects.filter(conference=conference, processedat__isnull=True).exists(),
        })
    elif request.GET.get('op', None) == 'thumb':
        # Get a thumbnail -- or make one if it's not there
        t = get_object_or_404(ConferenceTweetQueue, conference=conference, pk=get_int_or_error(request.GET, 'id'))
        if not t.imagethumb:
            # Need to generate a thumbnail here. Thumbnails are always made in PNG!
            p = ImageFile.Parser()
            p.feed(bytes(t.image))
            p.close()
            im = p.image
            im.thumbnail((256, 256))
            b = io.BytesIO()
            im.save(b, "png")
            t.imagethumb = b.getvalue()
            t.save()

        resp = HttpResponse(content_type='image/png')
        resp.write(bytes(t.imagethumb))
        return resp

    # Maximum length from any of the configured providers
    providermaxlength = {
        m.provider.publicname: providers.get(m.provider).max_post_length
        for m in
        ConferenceMessaging.objects.select_related('provider').filter(conference=conference,
                                                                      broadcast=True,
                                                                      provider__active=True)
    }

    return render(request, 'confreg/twitter.html', {
        'conference': conference,
        'reg': reg,
        'poster': canpost and 1 or 0,
        'directposter': canpostdirect and 1 or 0,
        'moderator': canmoderate and 1 or 0,
        'providerlengths': ", ".join(["{}: {}".format(k, v) for k, v in providermaxlength.items()]),
        'maxlength': max((v for k, v in providermaxlength.items())),
    })
