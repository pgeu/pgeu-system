from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from postgresqleu.confreg.models import MessagingProvider
from postgresqleu.util.messaging import get_messaging
from postgresqleu.util.messaging.twitter import process_twitter_webhook


@csrf_exempt
def messaging_webhook(request, providerid, token):
    provider = get_object_or_404(MessagingProvider, id=providerid, config__webhook__token=token)
    impl = get_messaging(provider)
    return impl.process_webhook(request)


# Twitter needs a special webhook URL since it's global and not per provider
@csrf_exempt
def twitter_webhook(request):
    return process_twitter_webhook(request)
