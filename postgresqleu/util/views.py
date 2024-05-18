from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, Http404

from postgresqleu.confreg.models import MessagingProvider
from postgresqleu.util.messaging import get_messaging
from postgresqleu.util.messaging.twitter import process_twitter_webhook
from postgresqleu.util.markup import pgmarkdown

import json


# Anybody logged in can do a markdown preview, since it's a safe operation
# and this way we don't need any db access.
@login_required
@csrf_exempt
def markdown_preview(request):
    if request.method != 'POST':
        return HttpResponse("POST only please", status=405)

    if request.headers.get('x-preview', None) != 'md':
        raise Http404()

    return HttpResponse(pgmarkdown(request.body.decode('utf8', 'ignore')))


@csrf_exempt
def oauth_return(request, providerid):
    if 'code' not in request.GET:
        raise Http404('Code missing')

    provider = get_object_or_404(MessagingProvider, id=providerid)
    impl = get_messaging(provider)
    if hasattr(impl, 'oauth_return'):
        err = impl.oauth_return(request)
        if err:
            return HttpResponse(err)
        else:
            if povider.series__id:
                return HttpResponseRedirect('{}/events/admin/_series/{}/messaging/{}/'.format(
                    settings.SITEBASE,
                    provider.series_id,
                    provider.id,
                ))
            else:
                return HttpResponseRedirect('{}/events/admin/news/messagingproviders/{}/'.format(
                    settings.SITEBASE,
                    provider.id,
                ))

    else:
        return HttpResponse('Unconfigured')


@csrf_exempt
def messaging_webhook(request, providerid, token):
    provider = get_object_or_404(MessagingProvider, id=providerid, config__webhook__token=token)
    impl = get_messaging(provider)
    return impl.process_webhook(request)


# Twitter needs a special webhook URL since it's global and not per provider
@csrf_exempt
def twitter_webhook(request):
    return process_twitter_webhook(request)


# Assetlinks to confirm to Google Play that we are the authors of our Android app
# (contents of file are suggestions from google play console)
def assetlinks(request):
    return HttpResponse(
        json.dumps([
            {
                "relation": [
                    "delegate_permission/common.handle_all_urls"
                ],
                "target": {
                    "namespace": "android_app",
                    "package_name": "eu.postgresql.android.conferencescanner",
                    "sha256_cert_fingerprints": [
                        "F3:F7:29:8B:4D:B4:2E:9E:B8:3B:C6:E3:8B:C0:69:FE:19:9E:2C:24:D4:6B:AE:C7:1E:83:D7:07:47:7E:CA:EB"
                    ]
                }
            }
        ]), content_type='application/json')
