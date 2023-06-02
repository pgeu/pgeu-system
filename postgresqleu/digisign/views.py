from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.conf import settings

from postgresqleu.util.decorators import global_login_exempt
from postgresqleu.digisign.models import DigisignProvider
from postgresqleu.mailqueue.util import send_simple_mail


@global_login_exempt
@csrf_exempt
def webhook(request, providershort, id):
    if request.method != 'POST':
        raise Http404()

    provider = get_object_or_404(DigisignProvider, pk=id)
    impl = provider.get_implementation()

    if impl.webhookcode != providershort:
        raise Http404()

    try:
        with transaction.atomic():
            impl.process_webhook(request)
        return HttpResponse("OK", status=200)
    except Exception as e:
        # Bad choice of address to send to, but it's the best we can do at this stage
        # as we don't have a general notifications address.
        send_simple_mail(
            settings.INVOICE_SENDER_EMAIL,
            settings.INVOICE_SENDER_EMAIL,
            "Exception processing digital signature webhook",
            "An exception occurred while processing a digital signature webhook for {}:\n\n{}\n".format(
                provider.name,
                e),
        )
        return HttpResponse("ERROR", status=500)
