from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

import base64
from datetime import timedelta
from decimal import Decimal
import requests

from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.util.decorators import global_login_exempt
from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod
from postgresqleu.invoices.util import InvoiceManager

from .models import RawNotification, AdyenLog, ReturnAuthorizationStatus
from .util import process_raw_adyen_notification


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


# Handle an Adyen payment (both credit card primary step and iban secondary step)
def _invoice_payment(request, methodid, invoice, trailer):
    method = get_object_or_404(InvoicePaymentMethod, active=True, pk=methodid)
    pm = method.get_implementation()

    if trailer == 'return/':
        # This is a payment return URL, so we wait for the status to be posted.
        if invoice.ispaid:
            # Success, this invoice is paid!
            return HttpResponseRedirect(InvoiceManager().get_invoice_return_url(invoice))

        # Else we wait for it to be. Return the pending page which will auto-refresh itself.
        # We sneakily use the "pspReference" field and put the invoice id in it, because that will never
        # conflict with an actual Adyen pspReference.
        status, created = ReturnAuthorizationStatus.objects.get_or_create(pspReference='INVOICE{}'.format(invoice.id))
        status.seencount += 1
        status.save()
        return render(request, 'adyen/authorized.html', {
            'refresh': 3**status.seencount,
            'returnurl': InvoiceManager().get_invoice_return_url(invoice),
        })

    if trailer == 'iban/':
        methods = ['bankTransfer_IBAN']
    else:
        methods = ['card']

    # Not the return handler, so use the Adyen checkout API to build a payment link.
    p = {
        'reference': '{}{}'.format(pm.config('merchantref_prefix'), invoice.id),
        'amount': {
            'value': int(invoice.total_amount * Decimal(100.0)),
            'currency': 'EUR',
        },
        'description': invoice.invoicestr,
        'merchantAccount': pm.config('merchantaccount'),
        'allowedPaymentMethods': methods,
        'returnUrl': '{}/invoices/adyenpayment/{}/{}/{}/return/'.format(settings.SITEBASE, methodid, invoice.id, invoice.recipient_secret),
    }
    if invoice.canceltime and invoice.canceltime < timezone.now() + timedelta(hours=24):
        p['expiresAt']: invoice.canceltime.isoformat(timespec='seconds')

    try:
        r = requests.post(
            '{}/v68/paymentLinks'.format(pm.config('checkoutbaseurl').rstrip('/')),
            json=p,
            headers={
                'x-api-key': pm.config('ws_apikey'),
            },
            timeout=10,
        )
        if r.status_code != 201:
            AdyenLog(pspReference='', message='Status code {} when trying to create a payment link. Response: {}'.format(r.status_code, r.text), error=True, paymentmethod=method).save()
            return HttpResponse('Failed to create payment link. Please try again later.')

        j = r.json()

        AdyenLog(pspReference='', message='Created payment link {} for invoice {}'.format(j['id'], invoice.id), error=False, paymentmethod=method).save()

        # Then redirect the user to the payment link we received
        return HttpResponseRedirect(j['url'])
    except requests.exceptions.ReadTimeout:
        AdyenLog(pspReference='', message='timeout when trying to create a payment link', error=True, paymentmethod=method).save()
        return HttpResponse('Failed to create payment link. Please try again later.')
    except Exception as e:
        AdyenLog(pspReference='', message='Exception when trying to create a payment link:{}'.format(e), error=True, paymentmethod=method).save()
        return HttpResponse('Failed to create payment link. Please try again later.')


@login_required
def invoicepayment(request, methodid, invoiceid, isreturn=None):
    invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True)
    if invoice.recipient_user != request.user:
        authenticate_backend_group(request, 'Invoice managers')

    return _invoice_payment(request, methodid, invoice, isreturn)


def invoicepayment_secret(request, methodid, invoiceid, secret, isreturn=None):
    invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True, recipient_secret=secret)
    return _invoice_payment(request, methodid, invoice, isreturn)


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
