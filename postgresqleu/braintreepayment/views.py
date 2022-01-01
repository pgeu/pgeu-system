from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseRedirect
from django.conf import settings
from django.utils import timezone
from django.db import transaction

from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.util.request import get_int_or_error
from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.mailqueue.util import send_simple_mail

from .models import BraintreeTransaction, BraintreeLog


class BraintreeProcessingException(Exception):
    pass


def payment_post(request):
    nonce = request.POST['payment_method_nonce']
    invoice = get_object_or_404(Invoice, pk=get_int_or_error(request.POST, 'invoice'), deleted=False, finalized=True)
    method = get_object_or_404(InvoicePaymentMethod, pk=get_int_or_error(request.POST, 'method'), active=True)
    pm = method.get_implementation()

    returnurl = InvoiceManager().get_invoice_return_url(invoice)

    # Generate the transaction
    result = pm.braintree_sale({
        'amount': '{0}'.format(invoice.total_amount),
        'order_id': '#{0}'.format(invoice.pk),
        'payment_method_nonce': nonce,
        'merchant_account_id': pm.config('merchantacctid'),
        'options': {
            'submit_for_settlement': True,
        }
    })

    trans = result.transaction
    if result.is_success:
        # Successful transaction. Store it for later processing. At authorization, we proceed to
        # flag the payment as done.

        BraintreeLog(transid=trans.id,
                     message='Received successful result for {0}'.format(trans.id),
                     paymentmethod=method).save()

        if trans.currency_iso_code != settings.CURRENCY_ISO:
            BraintreeLog(transid=trans.id,
                         error=True,
                         message='Invalid currency {0}, should be {1}'.format(trans.currency_iso_code, settings.CURRENCY_ISO),
                         paymentmethod=method).save()

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Invalid currency received in Braintree payment',
                             'Transaction {0} paid in {1}, should be {2}.'.format(trans.id, trans.currency_iso_code, settings.CURRENCY_ISO))

            # We'll just throw the "processing error" page, and have
            # the operator deal with the complaints as this is a
            # should-never-happen scenario.
            return render(request, 'braintreepayment/processing_error.html')

        with transaction.atomic():
            # Flag the invoice as paid
            manager = InvoiceManager()
            try:
                def invoice_logger(msg):
                    raise BraintreeProcessingException('Invoice processing failed: %s'.format(msg))

                manager.process_incoming_payment_for_invoice(invoice,
                                                             trans.amount,
                                                             'Braintree id {0}'.format(trans.id),
                                                             0,
                                                             pm.config('accounting_authorized'),
                                                             0,
                                                             [],
                                                             invoice_logger,
                                                             method,
                                                         )
            except BraintreeProcessingException as ex:
                send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                                 pm.config('notification_receiver'),
                                 'Exception occurred processing Braintree result',
                                 "An exception occured processing the payment result for {0}:\n\n{1}\n".format(trans.id, ex))

                return render(request, 'braintreepayment/processing_error.html')

            # Create a braintree transaction - so we can update it later when the transaction settles
            bt = BraintreeTransaction(transid=trans.id,
                                      authorizedat=timezone.now(),
                                      amount=trans.amount,
                                      method=trans.credit_card['card_type'],
                                      paymentmethod=method)
            if invoice.accounting_object:
                bt.accounting_object = invoice.accounting_object
            bt.save()

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Braintree payment authorized',
                             "A payment of %s%s with reference %s was authorized on the Braintree platform for %s.\nInvoice: %s\nRecipient name: %s\nRecipient user: %s\nBraintree reference: %s\n" % (
                                 settings.CURRENCY_ABBREV,
                                 trans.amount,
                                 trans.id,
                                 method.internaldescription,
                                 invoice.title,
                                 invoice.recipient_name,
                                 invoice.recipient_email,
                                 trans.id))

        return HttpResponseRedirect(returnurl)
    else:
        if not trans:
            reason = "Internal error"
        elif trans.status == 'processor_declined':
            reason = "Processor declined: {0}/{1}".format(trans.processor_response_code, trans.processor_response_text)
        elif trans.status == 'gateway_rejected':
            reason = "Gateway rejected: {0}".format(trans.gateway_rejection_reason)
        else:
            reason = "unknown"
        BraintreeLog(transid=trans and trans.id or "UNKNOWN",
                     message='Received FAILED result for {0}'.format(trans and trans.id or "UNKNOWN"),
                     error=True, paymentmethod=method).save()

        return render(request, 'braintreepayment/payment_failed.html', {
            'invoice': invoice,
            'reason': reason,
            'url': returnurl,
        })


def _invoice_payment(request, paymentmethodid, invoice):
    method = get_object_or_404(InvoicePaymentMethod, pk=paymentmethodid, active=True)
    pm = method.get_implementation()
    if not pm.braintree_ok:
        return Http404("Braintree module not loaded")

    token = pm.generate_client_token()

    return render(request, 'braintreepayment/invoice_payment.html', {
        'invoice': invoice,
        'paymentmethodid': method.id,
        'token': token,
    })


@login_required
def invoicepayment(request, paymentmethodid, invoiceid):
    invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True)
    if invoice.recipient_user != request.user:
        authenticate_backend_group(request, 'Invoice managers')

    return _invoice_payment(request, paymentmethodid, invoice)


def invoicepayment_secret(request, paymentmethodid, invoiceid, secret):
    invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True, recipient_secret=secret)
    return _invoice_payment(request, paymentmethodid, invoice)
