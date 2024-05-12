from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings

import json
import hmac
import hashlib
from decimal import Decimal

from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.invoices.util import is_managed_bank_account
from postgresqleu.invoices.util import register_pending_bank_matcher
from postgresqleu.util.decorators import global_login_exempt
from postgresqleu.util.currency import format_currency
from postgresqleu.accounting.util import create_accounting_entry
from postgresqleu.mailqueue.util import send_simple_mail

from .models import StripeCheckout, StripeRefund, StripePayout, StripeLog
from .models import ReturnAuthorizationStatus
from .api import StripeApi
from .util import process_stripe_checkout


@transaction.atomic
def invoicepayment_secret(request, paymentmethod, invoiceid, secret):
    method = get_object_or_404(InvoicePaymentMethod, pk=paymentmethod, active=True)
    invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True, recipient_secret=secret)

    pm = method.get_implementation()

    api = StripeApi(pm)

    try:
        co = StripeCheckout.objects.get(invoiceid=invoice.id)
        if co.completedat:
            # Session exists and is completed! Redirect to the invoice page that shows
            # the results.
            # This is a case that normally shouldn't happen, but can for example if a
            # user has multiple tabs open.
            return HttpResponseRedirect("/invoices/{0}/{1}/".format(invoice.id, invoice.recipient_secret))

        # Else session exists but is not completed, so send it through back to Stripe
        # again.
    except StripeCheckout.DoesNotExist:
        # Create a new checkout session
        co = StripeCheckout(createdat=timezone.now(),
                            paymentmethod=method,
                            invoiceid=invoice.id,
                            amount=invoice.total_amount)

        # Generate the session
        r = api.secret('checkout/sessions', {
            'cancel_url': '{0}/invoices/stripepay/{1}/{2}/{3}/cancel/'.format(settings.SITEBASE, paymentmethod, invoiceid, secret),
            'success_url': '{0}/invoices/stripepay/{1}/{2}/{3}/results/'.format(settings.SITEBASE, paymentmethod, invoiceid, secret),
            'payment_method_types': ['card', ],
            'client_reference_id': invoice.id,
            'line_items': [
                {
                    'amount': int(invoice.total_amount * 100),
                    'currency': settings.CURRENCY_ISO,
                    'name': '{0} invoice #{1}'.format(settings.ORG_NAME, invoice.id),
                    'quantity': 1,
                },
            ],
            'customer_email': invoice.recipient_email,
            'payment_intent_data': {
                'capture_method': 'automatic',
                'statement_descriptor': '{0} invoice {1}'.format(settings.ORG_SHORTNAME, invoice.id),
            },
        })
        if r.status_code != 200:
            return HttpResponse("Unable to create Stripe payment session: {}".format(r.status_code))
        j = r.json()
        co.sessionid = j['id']
        co.paymentintent = j['payment_intent']
        co.save()

    return render(request, 'stripepayment/payment.html', {
        'invoice': invoice,
        'stripekey': pm.config('published_key'),
        'sessionid': co.sessionid,
    })


def invoicepayment_results(request, paymentmethod, invoiceid, secret):
    # Get the invoice so we can be sure that we have the secret
    get_object_or_404(Invoice, id=invoiceid, recipient_secret=secret)
    co = get_object_or_404(StripeCheckout, invoiceid=invoiceid)

    if co.completedat:
        # Payment is completed!
        return HttpResponseRedirect("/invoices/{0}/{1}/".format(invoiceid, secret))

    # Else we need to loop on this page. To handle this we create
    # a temporary object so we can increase the waiting time
    status, created = ReturnAuthorizationStatus.objects.get_or_create(checkoutid=co.id)
    status.seencount += 1
    status.save()
    return render(request, 'stripepayment/pending.html', {
        'refresh': 3 * status.seencount,
        'url': '/invoices/stripepay/{0}/{1}/{2}/'.format(paymentmethod, invoiceid, secret),
        'createdat': co.createdat,
    })


def invoicepayment_cancel(request, paymentmethod, invoiceid, secret):
    # Get the invoice so we can be sure that we have the secret
    get_object_or_404(Invoice, id=invoiceid, recipient_secret=secret)
    co = get_object_or_404(StripeCheckout, invoiceid=invoiceid)
    method = InvoicePaymentMethod.objects.get(pk=paymentmethod, classname="postgresqleu.util.payment.stripe.Stripe")

    if not co.completedat:
        # Payment is not completed, so delete ours session.
        # Stripe API has no way to delete it on their end, but as soon as we have
        # removed our reference to it, it will never be used again.
        with transaction.atomic():
            StripeLog(message="Payment for Stripe checkout {0} (id {1}) canceled, removing.".format(co.id, co.sessionid),
                      paymentmethod=method).save()
            co.delete()

    # Send the user back to the invoice to pick another payment method (optionally)
    return HttpResponseRedirect("/invoices/{0}/{1}/".format(invoiceid, secret))


@csrf_exempt
@global_login_exempt
def webhook(request, methodid):
    sig = request.META['HTTP_STRIPE_SIGNATURE']
    try:
        payload = json.loads(request.body.decode('utf8', errors='ignore'))
    except ValueError:
        return HttpResponse("Invalid JSON", status=400)

    method = InvoicePaymentMethod.objects.get(pk=methodid, classname="postgresqleu.util.payment.stripe.Stripe")
    pm = method.get_implementation()

    sigdata = dict([v.strip().split('=') for v in sig.split(',')])

    sigstr = sigdata['t'] + '.' + request.body.decode('utf8', errors='ignore')
    mac = hmac.new(pm.config('webhook_secret').encode('utf8'),
                   msg=sigstr.encode('utf8'),
                   digestmod=hashlib.sha256)
    if mac.hexdigest() != sigdata['v1']:
        return HttpResponse("Invalid signature", status=400)

    # Signature is OK, figure out what to do
    if payload['type'] == 'checkout.session.completed':
        sessionid = payload['data']['object']['id']
        try:
            co = StripeCheckout.objects.get(sessionid=sessionid)
        except StripeCheckout.DoesNotExist:
            StripeLog(message="Received completed session event for non-existing sessions {}".format(sessionid),
                      error=True,
                      paymentmethod=method).save()
            return HttpResponse("OK")

        # We don't get enough data in the session, unfortunately, so we have to
        # make some incoming API calls.
        StripeLog(message="Received Stripe webhook for checkout {}. Processing.".format(co.id), paymentmethod=method).save()
        process_stripe_checkout(co)
        StripeLog(message="Completed processing webhook for checkout {}.".format(co.id), paymentmethod=method).save()
        return HttpResponse("OK")
    elif payload['type'] == 'charge.refunded':
        chargeid = payload['data']['object']['id']
        amount = Decimal(payload['data']['object']['amount_refunded']) / 100

        # Stripe stopped including the refund id in the refund
        # notification, and requires an extra API call to get
        # it. Instead of doing that, since we have the charge id we
        # can match it on that specific charge and the amount of the
        # refund. This could potentially return multiple entries in
        # case there is more than one refund made on the same charge
        # before the webhook fires, but we'll just say that's unlikely
        # enough we don't have to care about it.
        try:
            refund = StripeRefund.objects.get(
                paymentmethod=method,
                chargeid=chargeid,
                amount=amount,
            )
        except StripeRefund.DoesNotExist:
            StripeLog(
                message="Received completed refund event for charge {} with amount {} which could not be found in the database. Event has been acknowledged, but refund not marked as completed!",
                error=True,
                paymentmethod=method,
            ).save()
            return HttpResponse("OK")
        except StripeRefund.MultipleObjectsReturned:
            StripeLog(
                message="Received completed refund event for charge {} with amount {} which matched multiple entries. Event has been acknowledged, but refund not marked as completed!",
                error=True,
                paymentmethod=method,
            ).save()

        if refund.completedat:
            StripeLog(message="Received duplicate Stripe webhook for refund {}, ignoring.".format(refund.id), paymentmethod=method).save()
        else:
            # If it's not already processed, flag it as done and trigger the process.

            StripeLog(message="Received Stripe webhook for refund {}. Processing.".format(refund.id), paymentmethod=method).save()

            refund.completedat = timezone.now()
            refund.save(update_fields=['completedat'])

            manager = InvoiceManager()
            manager.complete_refund(
                refund.invoicerefundid_id,
                refund.amount,
                0,  # Unknown fee
                pm.config('accounting_income'),
                pm.config('accounting_fee'),
                [],
                method)
        return HttpResponse("OK")
    elif payload['type'] == 'payout.paid':
        # Payout has left Stripe. Should include both automatic and manual ones
        payoutid = payload['data']['object']['id']

        obj = payload['data']['object']
        if obj['currency'].lower() != settings.CURRENCY_ISO.lower():
            StripeLog(message="Received payout in incorrect currency {}, ignoring".format(obj['currency']),
                      error=True,
                      paymentmethod=method).save()
            return HttpResponse("OK")

        with transaction.atomic():
            if StripePayout.objects.filter(payoutid=payoutid).exists():
                StripeLog(message="Received duplicate notification for payout {}, ignoring".format(payoutid),
                          error=True,
                          paymentmethod=method).save()
                return HttpResponse("OK")

            payout = StripePayout(paymentmethod=method,
                                  payoutid=payoutid,
                                  amount=Decimal(obj['amount']) / 100,
                                  sentat=timezone.now(),
                                  description=obj['description'])
            payout.save()

            acctrows = [
                (pm.config('accounting_income'), 'Stripe payout {}'.format(payout.payoutid), -payout.amount, None),
                (pm.config('accounting_payout'), 'Stripe payout {}'.format(payout.payoutid), payout.amount, None),
            ]

            if is_managed_bank_account(pm.config('accounting_payout')):
                entry = create_accounting_entry(acctrows, True)

                # Stripe payouts include a "magic number", but unfortunately this magic number
                # is not available through the APIs so there is no way to match on it.
                register_pending_bank_matcher(pm.config('accounting_payout'),
                                              r'.*STRIPE(\s+[^\s+].*|$)',
                                              payout.amount,
                                              entry)
                msg = "A Stripe payout of {} with description {} completed for {}.\n\nAccounting entry {} was created and will automatically be closed once the payout has arrived.".format(
                    format_currency(payout.amount),
                    payout.description,
                    method.internaldescription,
                    entry,
                )
            else:
                msg = "A Stripe payout of {} with description {} completed for {}.\n".format(
                    format_currency(payout.amount),
                    payout.description,
                    method.internaldescription,
                )

            StripeLog(message=msg, paymentmethod=method).save()
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Stripe payout completed',
                             msg,
            )
            return HttpResponse("OK")
    else:
        StripeLog(message="Received unknown Stripe event type '{}'".format(payload['type']),
                  error=True,
                  paymentmethod=method).save()
        # We still flag it as OK to stripe
        return HttpResponse("OK")
