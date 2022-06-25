from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, Http404

from postgresqleu.confreg.models import MessagingProvider
from postgresqleu.util.messaging import get_messaging
from postgresqleu.util.messaging.twitter import process_twitter_webhook
from postgresqleu.util.markup import pgmarkdown


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
def messaging_webhook(request, providerid, token):
    provider = get_object_or_404(MessagingProvider, id=providerid, config__webhook__token=token)
    impl = get_messaging(provider)
    return impl.process_webhook(request)


# Twitter needs a special webhook URL since it's global and not per provider
@csrf_exempt
def twitter_webhook(request):
    return process_twitter_webhook(request)
