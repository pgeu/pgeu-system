from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.conf import settings
from django.db import transaction

from datetime import datetime

import braintree

from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.mailqueue.util import send_simple_mail

from models import BraintreeTransaction, BraintreeLog
from util import initialize_braintree

class BraintreeProcessingException(Exception):
    pass

def payment_post(request):
    nonce = request.POST['payment_method_nonce']
    invoice = get_object_or_404(Invoice, pk=request.POST['invoice'], deleted=False, finalized=True)

    if invoice.processor:
        manager = InvoiceManager()
        processor = manager.get_invoice_processor(invoice)
        returnurl = processor.get_return_url(invoice)
    else:
        if invoice.recipient_user:
            returnurl = "%s/invoices/%s/" % (settings.SITEBASE, invoice.pk)
        else:
            returnurl = "%s/invoices/%s/%s/" % (settings.SITEBASE, invoice.pk, invoice.recipient_secret)

    # Generate the transaction
    initialize_braintree()
    result = braintree.Transaction.sale({
        'amount': '{0}'.format(invoice.total_amount),
        'order_id': '#{0}'.format(invoice.pk),
        'payment_method_nonce': nonce,
        'options' : {
            'submit_for_settlement': True,
        }
    })

    trans = result.transaction
    if result.is_success:
        # Successful transaction. Store it for later processing. At authorization, we proceed to
        # flag the payment as done.

        BraintreeLog(transid=trans.id,
                     message='Received successful result for {0}'.format(trans.id)).save()

        if trans.currency_iso_code != settings.CURRENCY_ISO:
            BraintreeLog(transid=trans.id,
                         error=True,
                         message='Invalid currency {0}, should be {1}'.format(trans.currency_iso_code, settings.CURRENCY_ISO)).save()

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             settings.BRAINTREE_NOTIFICATION_RECEIVER,
                             'Invalid currency received in Braintree payment',
                             'Transaction {0} paid in {1}, should be {2}.'.format(trans.id, trans.currency_iso_code, settings.CURRENCY_ISO))

            # We'll just throw the "processing error" page, and have
            # the operator deal with the complaints as this is a
            # should-never-happen scenario.
            return render(request, 'braintreepayment/processing_error.html', {
                'contact': settings.INVOICE_SENDER_EMAIL,
            })


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
                                                             settings.ACCOUNTING_BRAINTREE_AUTHORIZED_ACCOUNT,
                                                             0,
                                                             [],
                                                             invoice_logger,
                                                             InvoicePaymentMethod.objects.get(classname='postgresqleu.util.payment.braintree.Braintree'),
                                                         )
            except BraintreeProcessingException, ex:
                send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                                 settings.BRAINTREE_NOTIFICATION_RECEIVER,
                                 'Exception occurred processing Braintree result',
                                 "An exception occured processing the payment result for {0}:\n\n{1}\n".format(trans.id, ex))

                return render(request, 'braintreepayment/processing_error.html', {
                    'contact': settings.INVOICE_SENDER_EMAIL,
                })

            # Create a braintree transaction - so we can update it later when the transaction settles
            bt = BraintreeTransaction(transid=trans.id,
                                      authorizedat=datetime.now(),
                                      amount=trans.amount,
                                      method=trans.credit_card['card_type'])
            if invoice.accounting_object:
                bt.accounting_object = invoice.accounting_object
            bt.save()

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             settings.BRAINTREE_NOTIFICATION_RECEIVER,
                             'Braintree payment authorized',
                             "A payment of %s%s with reference %s was authorized on the Braintree platform.\nInvoice: %s\nRecipient name: %s\nRecipient user: %s\nBraintree reference: %s\n" % (settings.CURRENCY_ABBREV, trans.amount, trans.id, invoice.title, invoice.recipient_name, invoice.recipient_email, trans.id))

        return HttpResponseRedirect(returnurl)
    else:
        if trans.status == 'processor_declined':
            reason = "Processor declined: {0}/{1}".format(trans.processor_response_code, trans.processor_response_text)
        elif trans.status == 'gateway_rejected':
            reason = "Gateway rejected: {0}".format(trans.gateway_rejection_reason)
        else:
            reason = "unknown"
        BraintreeLog(transid=trans.id,
                     message='Received FAILED result for {0}'.format(trans.id),
                     error=True).save()

        return render(request, 'braintreepayment/payment_failed.html', {
            'invoice': invoice,
            'reason': reason,
            'url': returnurl,
        })

def _invoice_payment(request, invoice):
    initialize_braintree()
    token = braintree.ClientToken.generate({})

    return render(request, 'braintreepayment/invoice_payment.html', {
        'invoice': invoice,
        'token': token,
    })

@login_required
def invoicepayment(request, invoiceid):
    invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True)
    if not (request.user.has_module_perms('invoices') or invoice.recipient_user == request.user):
        return HttpResponseForbidden("Access denied")

    return _invoice_payment(request, invoice)

def invoicepayment_secret(request, invoiceid, secret):
    invoice = get_object_or_404(Invoice, pk=invoiceid, deleted=False, finalized=True, recipient_secret=secret)
    return _invoice_payment(request, invoice)
