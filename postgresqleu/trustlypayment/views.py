from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

from datetime import datetime

from postgresqleu.invoices.models import Invoice

from .util import Trustly, TrustlyException
from .models import TrustlyTransaction, TrustlyRawNotification, TrustlyLog
from .models import ReturnAuthorizationStatus


@transaction.atomic
def invoicepayment_secret(request, invoiceid, secret):
    invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True, recipient_secret=secret)

    # If this payment has already been initiated, redirect back to existing URL
    try:
        t = TrustlyTransaction.objects.get(invoiceid=invoice.id, amount=invoice.total_amount)
        if t.pendingat:
            # This transaction is already started, so we need to redirect back to our own return URL
            return HttpResponseRedirect('{0}/trustly_success/{1}/{2}/'.format(settings.SITEBASE, invoice.id, invoice.recipient_secret))
        # Else it's not started, so we're going to abandon this one and create a new one
        TrustlyLog(message='Abandoning order {0} and starting over.'.format(t.orderid)).save()
        t.delete()
    except TrustlyTransaction.DoesNotExist:
        # Not processed, so get a new one
        pass

    # Make a call to the Trustly API to set up a payment.
    # XXX: should we have a verify step here? As in "hey, we're about to send you to Trustly"
    # XXX: should we use an iframe? For now just send everything there because it's easier..

    t = Trustly()

    try:
        if request.user and not request.user.is_anonymous():
            enduserid = request.user.username
            first = request.user.first_name
            last = request.user.last_name
            email = request.user.email
        else:
            first = last = email = None
            # For secret payments, use the invoice secret as the identifier
            enduserid = secret

        r = t.deposit(enduserid,
                      "{0}".format(invoice.id),
                      invoice.total_amount,
                      '{0}#{1}'.format(settings.ORG_SHORTNAME, invoice.id),
                      '{0}/trustly_success/{1}/{2}/'.format(settings.SITEBASE, invoice.id, invoice.recipient_secret),
                      '{0}/trustly_failure/{1}/{2}/'.format(settings.SITEBASE, invoice.id, invoice.recipient_secret),
                      first,
                      last,
                      email,
                      request.META['REMOTE_ADDR'])

        # Trustly request was successful, so we have an url to send the user to. Let's set up
        # the transaction on our end.

        TrustlyTransaction(createdat=datetime.now(),
                           invoiceid=invoice.id,
                           amount=invoice.total_amount,
                           orderid=r['data']['orderid'],
                           redirecturl=r['data']['url'],
        ).save()

        # With the transaction saved, redirect the user to Trustly
        return HttpResponseRedirect(r['data']['url'])
    except TrustlyException as e:
        return HttpResponse("Error communicating with Trustly: {0}".format(e))


def success(request, invoiceid, secret):
    # Get the invoice so we can be sure that we have the secret
    get_object_or_404(Invoice, id=invoiceid, recipient_secret=secret)
    trans = get_object_or_404(TrustlyTransaction, invoiceid=invoiceid)

    if trans.completedat:
        # Payment is completed, to redirect the user back to the invoice
        return HttpResponseRedirect("/invoices/{0}/{1}/".format(invoiceid, secret))

    # Else we need to loop on this page. To handle this we create
    # a temporary object so we can increase the waiting time
    status, created = ReturnAuthorizationStatus.objects.get_or_create(orderid=trans.orderid)
    status.seencount += 1
    status.save()
    return render(request, 'trustlypayment/pending.html', {
        'refresh': 3 * status.seencount,
        'url': '/invoices/{0}/{1}/'.format(invoiceid, secret),
        'createdat': trans.createdat,
        'pendingat': trans.pendingat,
    })


def failure(request, invoiceid, secret):
    return render(request, 'trustlypayment/error.html', {
        'url': '/invoices/{0}/{1}/'.format(invoiceid, secret),
    })


@csrf_exempt
def notification(request):
    raw = TrustlyRawNotification(contents=request.body)
    raw.save()

    t = Trustly()

    (ok, uuid, method) = t.process_raw_trustly_notification(raw)
    return HttpResponse(t.create_notification_response(uuid, method, ok and "OK" or "FAILED"),
                        content_type='application/json')
