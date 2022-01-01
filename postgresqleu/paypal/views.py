from django.http import HttpResponseForbidden, HttpResponse
from django.db import transaction
from django.shortcuts import render, get_object_or_404
from django.conf import settings
from django.utils import timezone

from decimal import Decimal
from urllib.parse import unquote_plus
import requests

from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.accounting.util import create_accounting_entry

from .models import TransactionInfo, ErrorLog


@transaction.atomic
def paypal_return_handler(request, methodid):
    tx = 'UNKNOWN'

    method = get_object_or_404(InvoicePaymentMethod, pk=int(methodid), active=True)
    pm = method.get_implementation()

    # Custom error return that can get to the request context
    def paypal_error(reason):
        return render(request, 'paypal/error.html', {
            'reason': reason,
        })

    # Logger for the invoice processing - we store it in the genereal
    # paypal logs
    def payment_logger(msg):
        ErrorLog(timestamp=timezone.now(),
                 sent=False,
                 message='Paypal automatch for %s: %s' % (tx, msg),
                 paymentmethod=method,
                 ).save()

    # Now for the main handler

    # Handle a paypal PDT return
    if 'tx' not in request.GET:
        return paypal_error('Transaction id not received from paypal')

    tx = request.GET['tx']
    # We have a transaction id. First we check if we already have it
    # in the database.
    # We only store transactions with status paid, so if it's in there,
    # then it's already paid, and what's happening here is a replay
    # (either by mistake or intentional). So we don't redirect the user
    # at this point, we just give an error message.
    try:
        ti = TransactionInfo.objects.get(paypaltransid=tx)
        return HttpResponseForbidden('This transaction has already been processed')
    except TransactionInfo.DoesNotExist:
        pass

    # We haven't stored the status of this transaction. It either means
    # this is the first load, or that we have only seen pending state on
    # it before. Thus, we need to post back to paypal to figure out the
    # current status.
    try:
        params = {
            'cmd': '_notify-synch',
            'tx': tx,
            'at': pm.config('pdt_token'),
            }
        resp = requests.post(pm.get_baseurl(), data=params)
        if resp.status_code != 200:
            raise Exception("status code {0}".format(resp.status_code))
        r = resp.text
    except Exception as ex:
        # Failed to talk to paypal somehow. It should be ok to retry.
        return paypal_error('Failed to verify status with paypal: %s' % ex)

    # First line of paypal response contains SUCCESS if we got a valid
    # response (which might *not* mean it's actually a payment!)
    lines = r.split("\n")
    if lines[0] != 'SUCCESS':
        return paypal_error('Received an error from paypal.')

    # Drop the SUCCESS line
    lines = lines[1:]

    # The rest of the response is urlencoded key/value pairs
    d = dict([unquote_plus(line).split('=') for line in lines if line != ''])

    # Validate things that should never be wrong
    try:
        if d['txn_id'] != tx:
            return paypal_error('Received invalid transaction id from paypal')
        if d['txn_type'] != 'web_accept':
            return paypal_error('Received transaction type %s which is unknown by this system!' % d['txn_type'])
        if d['business'] != pm.config('email'):
            return paypal_error('Received payment for %s which is not the correct recipient!' % d['business'])
        if d['mc_currency'] != settings.CURRENCY_ABBREV:
            return paypal_error('Received payment in %s, not %s. We cannot currently process this automatically.' % (d['mc_currency'], settings.CURRENCY_ABBREV))
    except KeyError as k:
        return paypal_error('Mandatory field %s is missing from paypal data!', k)

    # Now let's find the state of the payment
    if 'payment_status' not in d:
        return paypal_error('Payment status not received from paypal!')

    if d['payment_status'] == 'Completed':
        # Payment is completed. Create a paypal transaction info
        # object for it, and then try to match it to an invoice.

        # Double-check if it is already added. We did check this furter
        # up, but it seems it can sometimes be called more than once
        # asynchronously, due to the check with paypal taking too
        # long.
        if TransactionInfo.objects.filter(paypaltransid=tx).exists():
            return HttpResponse("Transaction already processed", content_type='text/plain')

        # Paypal seems to randomly change which field actually contains
        # the transaction title.
        if d.get('transaction_subject', ''):
            transtext = d['transaction_subject']
        else:
            transtext = d['item_name']
        ti = TransactionInfo(paypaltransid=tx,
                             timestamp=timezone.now(),
                             paymentmethod=method,
                             sender=d['payer_email'],
                             sendername=d['first_name'] + ' ' + d['last_name'],
                             amount=Decimal(d['mc_gross']),
                             fee=Decimal(d['mc_fee']),
                             transtext=transtext,
                             matched=False)
        ti.save()

        # Generate URLs that link back to paypal in a way that we can use
        # from the accounting system. Note that this is an undocumented
        # URL format for paypal, so it may stop working at some point in
        # the future.
        urls = ["%s?cmd=_view-a-trans&id=%s" % (pm.get_baseurl(), ti.paypaltransid, ), ]

        # Separate out donations made through our website
        if ti.transtext == pm.config('donation_text'):
            ti.matched = True
            ti.matchinfo = 'Donation, automatically matched'
            ti.save()

            # Generate a simple accounting record, that will have to be
            # manually completed.
            accstr = "Paypal donation %s" % ti.paypaltransid
            accrows = [
                (pm.config('accounting_income'), accstr, ti.amount - ti.fee, None),
                (pm.config('accounting_fee'), accstr, ti.fee, None),
                (settings.ACCOUNTING_DONATIONS_ACCOUNT, accstr, -ti.amount, None),
                ]
            create_accounting_entry(accrows, True, urls)

            return render(request, 'paypal/noinvoice.html', {
            })

        invoicemanager = InvoiceManager()
        (r, i, p) = invoicemanager.process_incoming_payment(ti.transtext,
                                                            ti.amount,
                                                            "Paypal id %s, from %s <%s>, auto" % (ti.paypaltransid, ti.sendername, ti.sender),
                                                            ti.fee,
                                                            pm.config('accounting_income'),
                                                            pm.config('accounting_fee'),
                                                            urls,
                                                            payment_logger,
                                                            method,
        )
        if r == invoicemanager.RESULT_OK:
            # Matched it!
            ti.matched = True
            ti.matchinfo = 'Matched standard invoice (auto)'
            ti.save()

            return render(request, 'paypal/complete.html', {
                'invoice': i,
                'url': invoicemanager.get_invoice_return_url(i),
            })
        else:
            # Did not match an invoice anywhere!
            # We'll leave the transaction in the paypal transaction
            # list, where it will generate an alert in the nightly mail.
            return render(request, 'paypal/noinvoice.html', {
            })

    # For a pending payment, we set ourselves up with a redirect loop
    if d['payment_status'] == 'Pending':
        try:
            pending_reason = d['pending_reason']
        except Exception as e:
            pending_reason = 'no reason given'
        return render(request, 'paypal/pending.html', {
            'reason': pending_reason,
        })
    return paypal_error('Unknown payment status %s.' % d['payment_status'])
