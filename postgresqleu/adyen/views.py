from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.db import transaction
from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt

import base64

from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.util.decorators import global_login_exempt
from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod
from postgresqleu.invoices.util import InvoiceManager

from .models import RawNotification, AdyenLog, ReturnAuthorizationStatus
from .util import process_raw_adyen_notification


@transaction.atomic
def adyen_return_handler(request, methodid):
    method = get_object_or_404(InvoicePaymentMethod, pk=methodid, active=True)
    pm = method.get_implementation()

    sig = pm.calculate_signature(request.GET)

    if sig != request.GET['merchantSig']:
        return render(request, 'adyen/sigerror.html')

    # We're going to need the invoice for pretty much everything,
    # so attempt to find it.
    if request.GET['merchantReturnData'] != request.GET['merchantReference'] or not request.GET['merchantReturnData'].startswith(pm.config('merchantref_prefix')):
        AdyenLog(pspReference='', message='Return handler received invalid reference %s/%s' % (request.GET['merchantReturnData'], request.GET['merchantReference']), error=True, paymentmethod=method).save()
        return render(request, 'adyen/invalidreference.html', {
            'reference': "%s//%s" % (request.GET['merchantReturnData'], request.GET['merchantReference']),
        })

    invoiceid = int(request.GET['merchantReturnData'][len(pm.config('merchantref_prefix')):])
    try:
        invoice = Invoice.objects.get(pk=invoiceid)
    except Invoice.DoesNotExist:
        AdyenLog(pspReference='', message='Return handler could not find invoice for reference %s' % request.GET['merchantReturnData'], error=True, paymentmethod=method).save()
        return render(request, 'adyen/invalidreference.html', {
            'reference': request.GET['merchantReturnData'],
        })
    returnurl = InvoiceManager().get_invoice_return_url(invoice)

    AdyenLog(pspReference='', message='Return handler received %s result for %s' % (request.GET['authResult'], request.GET['merchantReturnData']), error=False, paymentmethod=method).save()
    if request.GET['authResult'] == 'REFUSED':
        return render(request, 'adyen/refused.html', {
            'url': returnurl,
            })
    elif request.GET['authResult'] == 'CANCELLED':
        return HttpResponseRedirect(returnurl)
    elif request.GET['authResult'] == 'ERROR':
        return render(request, 'adyen/transerror.html', {
            'url': returnurl,
            })
    elif request.GET['authResult'] == 'PENDING':
        return render(request, 'adyen/pending.html', {
            'url': returnurl,
            })
    elif request.GET['authResult'] == 'AUTHORISED':
        # NOTE! Adyen strongly recommends not reacting on
        # authorized values, but deal with them from the
        # notifications instead. So we'll do that.
        # However, if we reach this point and it's actually
        # already dealt with by the notification arriving
        # asynchronously, redirect the user properly.
        if invoice.paidat:
            # Yup, it's paid, so send the user off to the page
            # that they came from.
            return HttpResponseRedirect(returnurl)

        # Show the user a pending message. The refresh time is dependent
        # on how many times we've seen this one before.
        status, created = ReturnAuthorizationStatus.objects.get_or_create(pspReference=request.GET['pspReference'])
        status.seencount += 1
        status.save()
        return render(request, 'adyen/authorized.html', {
            'refresh': 3**status.seencount,
            'url': returnurl,
            })
    else:
        return render(request, 'adyen/invalidresult.html', {
            'result': request.GET['authResult'],
            })


@global_login_exempt
@csrf_exempt
def adyen_notify_handler(request, methodid):
    # Handle asynchronous notifications from the Adyen payment platform
    method = get_object_or_404(InvoicePaymentMethod, pk=methodid, active=True)
    pm = method.get_implementation()

    # Authenticate with HTTP BASIC
    if 'HTTP_AUTHORIZATION' not in request.META:
        # Sometimes Adyen sends notifications without authorization headers.
        # In this case, we request authrorization and they will try again
        r = HttpResponse('Unauthorized', status=401)
        r['WWW-Authenticate'] = 'Basic realm="postgresqleu adyen"'
        return r

    auth = request.META['HTTP_AUTHORIZATION'].split()
    if len(auth) != 2:
        raise Exception('Adyen notification received with invalid length authentication')
    if auth[0].lower() != 'basic':
        raise Exception('Adyen notification received with invalid authentication type')
    user, pwd = base64.b64decode(auth[1]).decode('utf8').split(':')
    if user != pm.config('notify_user') or pwd != pm.config('notify_password'):
        return HttpResponseForbidden('Invalid username or password')

    # Ok, we have authentication. All our data is now available in
    # request.POST and request.body

    # Store the raw notification at this point, so we have it around in
    # case something breaks in a way we couldn't handle
    raw = RawNotification(contents=request.body.decode(), paymentmethod=method)
    raw.save()

    if process_raw_adyen_notification(raw, request.POST):
        return HttpResponse('[accepted]', content_type='text/plain')
    else:
        return HttpResponse('[internal error]', content_type='text/plain')


# Rendered views to do bank payment
def _bank_payment(request, methodid, invoice):
    method = get_object_or_404(InvoicePaymentMethod, active=True, pk=methodid)
    pm = method.get_implementation()
    paymenturl = pm.build_adyen_payment_url(invoice.invoicestr, invoice.total_amount, invoice.pk)
    return render(request, 'adyen/adyen_bank_payment.html', {
        'available': pm.available(invoice),
        'unavailable_reason': pm.unavailable_reason(invoice),
        'paymenturl': paymenturl,
    })


@login_required
def bankpayment(request, methodid, invoiceid):
    invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True)
    if invoice.recipient_user != request.user:
        authenticate_backend_group(request, 'Invoice managers')

    return _bank_payment(request, methodid, invoice)


def bankpayment_secret(request, methodid, invoiceid, secret):
    invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True, recipient_secret=secret)
    return _bank_payment(request, methodid, invoice)
