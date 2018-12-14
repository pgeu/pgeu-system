from django.conf import settings
from django.urls import reverse
from django.db import transaction

from datetime import datetime, date
from decimal import Decimal

import json
import urllib2
from base64 import standard_b64encode

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod
from postgresqleu.accounting.util import create_accounting_entry

from models import TransactionStatus, Report, AdyenLog, Notification, Refund

# Internal exception class
class AdyenProcessingException(Exception):
    pass


###
# Process notifications of different types. Expects to be
# called within a transaction context already.
###
def process_authorization(notification):
    if notification.success:
        # This is a successful notification, so flag this invoice
        # as paid. We also create a TransactionStatus for it, so that
        # can validate that it goes from authorized->captured.
        trans = TransactionStatus(pspReference=notification.pspReference,
                                  notification=notification,
                                  authorizedat=datetime.now(),
                                  amount=notification.amount,
                                  method=notification.paymentMethod,
                                  notes=notification.merchantReference,
                                  capturedat=None)
        trans.save()

        # Generate urls pointing back to this entry in the Adyen online
        # system, for inclusion in accounting records.
        urls = ["https://ca-live.adyen.com/ca/ca/accounts/showTx.shtml?pspReference=%s&txType=Payment&accountKey=MerchantAccount.%s" % (notification.pspReference, notification.merchantAccountCode), ]

        # We can receive authorizations on non-primary Adyen merchant
        # accounts. This happens for example with payments from POS
        # terminals. In those cases, just send an email, and don't
        # try to match it to any invoices.
        # We still store and track the transaction.
        if notification.merchantAccountCode != settings.ADYEN_MERCHANTACCOUNT:
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             settings.ADYEN_NOTIFICATION_RECEIVER,
                             'Manual Adyen payment authorized',
                             "An Adyen payment of %s%s was authorized on the Adyen platform.\nThis payment was not from the automated system, it was manually authorized, probably from a POS terminal.\nReference: %s\nAdyen reference: %s\nMerchant account: %s\n" % (settings.CURRENCY_ABBREV, notification.amount, notification.merchantReference, notification.pspReference, notification.merchantAccountCode))
            notification.confirmed = True
            notification.save()

            # For manual payments, we can only create an open-ended entry
            # in the accounting

            accstr = "Manual Adyen payment: %s (%s)" % (notification.merchantReference, notification.pspReference)
            accrows = [
                (settings.ACCOUNTING_ADYEN_AUTHORIZED_ACCOUNT, accstr, trans.amount, None),
            ]

            create_accounting_entry(date.today(), accrows, True, urls)
            return

        # Process a payment on the primary account
        manager = InvoiceManager()
        try:
            # Figure out the invoiceid
            if not notification.merchantReference.startswith(settings.ADYEN_MERCHANTREF_PREFIX):
                raise AdyenProcessingException('Merchant reference does not start with %s' % settings.ADYEN_MERCHANTREF_PREFIX)
            invoiceid = int(notification.merchantReference[len(settings.ADYEN_MERCHANTREF_PREFIX):])

            # Get the actual invoice
            try:
                invoice = Invoice.objects.get(pk=invoiceid)
            except Invoice.DoesNotExist:
                raise AdyenProcessingException('Invoice with id %s does not exist' % invoiceid)

            def invoice_logger(msg):
                invoice_logger.invoice_log += msg
                invoice_logger.invoice_log += "\n"
            invoice_logger.invoice_log = ""

            # Handle our special case of Adyen where we have two different processors
            # depending on what method was used at Adyen.
            if trans.method == 'bankTransfer_IBAN':
                method = InvoicePaymentMethod.objects.get(classname='postgresqleu.util.payment.adyen.AdyenBanktransfer')
            else:
                method = InvoicePaymentMethod.objects.get(classname='postgresqleu.util.payment.adyen.AdyenCreditcard')
            (status, _invoice, _processor) = manager.process_incoming_payment_for_invoice(invoice, notification.amount, 'Adyen id %s' % notification.pspReference, 0, settings.ACCOUNTING_ADYEN_AUTHORIZED_ACCOUNT, 0, urls, invoice_logger, method)
            if status != manager.RESULT_OK:
                # An error occurred, but nevertheless the money is in our account at this
                # point. The invoice itself will not have been flagged as paid since something
                # went wrong, and this also means no full accounting record has been created.
                # At this point we have no transaction cost, so we just have the payment itself.
                # Someone will manually have to figure out where to stick it.
                accrows = [
                    (settings.ACCOUNTING_ADYEN_AUTHORIZED_ACCOUNT, "Incorrect payment for invoice #{0}".format(invoice.id), notification.amount, None),
                ]
                create_accounting_entry(date.today(), accrows, True, urls)

                send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                                 settings.ADYEN_NOTIFICATION_RECEIVER,
                                 'Error processing invoice from Adyen notification',
                                 u"An error occured processing the notification for invoice #{0}.\n\nThe messages given were:\n{1}\n\nAn incomplete accounting record has been created, and the situation needs to be handled manually.\n".format(
                                     invoice.id,
                                     invoice_logger.invoice_log),
                )
                # Actually flag the notification as handled, so we don't end up repeating it.
                notification.confirmed = True
                notification.save()
                return


            if invoice.accounting_object:
                # Store the accounting object so we can properly tag the
                # fee for it when we process the settlement (since we don't
                # actually know the fee yet)
                trans.accounting_object = invoice.accounting_object
                trans.save()

            # If nothing went wrong, then this invoice is now fully
            # flagged as paid in the system.
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             settings.ADYEN_NOTIFICATION_RECEIVER,
                             'Adyen payment authorized',
                             "An Adyen payment of %s%s with reference %s was authorized on the Adyen platform.\nInvoice: %s\nRecipient name: %s\nRecipient user: %s\nPayment method: %s\nAdyen reference: %s\n" % (settings.CURRENCY_ABBREV, notification.amount, notification.merchantReference, invoice.title, invoice.recipient_name, invoice.recipient_email, notification.paymentMethod, notification.pspReference))

        except AdyenProcessingException, ex:
            # Generate an email telling us about this exception!
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             settings.ADYEN_NOTIFICATION_RECEIVER,
                             'Exception occured processing Adyen notification',
                             "An exception occurred processing the notification for %s:\n\n%s\n" % (
                                 notification.merchantReference,
                                 ex)
                         )
            # We have stored the notification already, but we want
            # to make sure it's not *confirmed*. That way it'll keep
            # bugging the user. So, return here instead of confirming
            # it.
            return
    else:
        send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                         settings.ADYEN_NOTIFICATION_RECEIVER,
                         'Unsuccessful Adyen authorization received',
                         "A credit card authorization for %s on account %s has failed.\nThe reason given was:\n%s\n\nYou don't need to take any further action, nothing has been confirmed in the systems." % (
                             notification.merchantReference,
                             notification.merchantAccountCode,
                             notification.reason,
                             )
                         )
    notification.confirmed = True
    notification.save()

def process_capture(notification):
    if notification.success:
        # Successful capture, so we just set when the capture happened
        try:
            ts = TransactionStatus.objects.get(pspReference=notification.originalReference)
            ts.capturedat = datetime.now()
            ts.save()
        except TransactionStatus.DoesNotExist:
            # We just ignore captures for non-existant transactions. This
            # seems to happen for example when a transaction is cancelled
            # on a POS terminal.
            pass
    else:
        send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                         settings.ADYEN_NOTIFICATION_RECEIVER,
                         'Unsuccessful adyen capture received',
                         "A credit card capture for %s has failed.\nThe reason given was:\n%s\n\nYou want to investigate this since the payment was probably flagged as completed on authorization!\n" % (
                             notification.merchantReference,
                             notification.reason))
    # We confirm the notification even if we sent it, since there is not much more we can do
    notification.confirmed = True
    notification.save()

def process_refund(notification):
    # Store the refund, and send an email!
    if notification.success:
        try:
            ts = TransactionStatus.objects.get(pspReference=notification.originalReference)
            refund = Refund(notification=notification, transaction=ts, refund_amount=notification.amount)
            refund.save()

            urls = [
                "https://ca-live.adyen.com/ca/ca/accounts/showTx.shtml?pspReference=%s&txType=Payment&accountKey=MerchantAccount.%s" % (notification.pspReference, notification.merchantAccountCode),
            ]

            # API generated refund?
            if notification.merchantReference.startswith(settings.ADYEN_MERCHANTREF_REFUND_PREFIX):
                # API generated
                invoicerefundid = int(notification.merchantReference[10:])

                # Get the correct method depending on how it was done
                if ts.method == 'bankTransfer_IBAN':
                    method = InvoicePaymentMethod.objects.get(classname='postgresqleu.util.payment.adyen.AdyenBanktransfer')
                else:
                    method = InvoicePaymentMethod.objects.get(classname='postgresqleu.util.payment.adyen.AdyenCreditcard')

                manager = InvoiceManager()
                manager.complete_refund(
                    invoicerefundid,
                    refund.refund_amount,
                    0, # we don't know the fee, it'll be generically booked
                    settings.ACCOUNTING_ADYEN_REFUNDS_ACCOUNT,
                    settings.ACCOUNTING_ADYEN_FEE_ACCOUNT,
                    urls,
                    method)

            else:
                # Generate an open accounting record for this refund.
                # We expect this happens so seldom that we can just deal with
                # manually finishing off the accounting records.

                accrows = [
                    (settings.ACCOUNTING_ADYEN_REFUNDS_ACCOUNT,
                     "Refund of %s (transaction %s) " % (ts.notes, ts.pspReference),
                     -refund.refund_amount,
                     None),
                ]

                send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                                 settings.ADYEN_NOTIFICATION_RECEIVER,
                                 'Adyen refund received',
                                 "A refund of %s%s for transaction %s was processed\n\nNOTE! You must complete the accounting system entry manually as it was not API generated!!" % (settings.CURRENCY_ABBREV, notification.amount, notification.originalReference))

                create_accounting_entry(date.today(), accrows, True, urls)

        except TransactionStatus.DoesNotExist:
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             settings.ADYEN_NOTIFICATION_RECEIVER,
                             'Adyen refund received for nonexisting transaction',
                             "A refund for %s was received, but the transaction does not exist!\n\nYou probably want to investigate this!\n" % notification.originalReference)
    else:
        send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                         settings.ADYEN_NOTIFICATION_RECEIVER,
                         'Unsuccessful adyen refund received',
                         "A refund for %s has failed.\nThe reason given was:\n%s\n\nYou probably want to investigate this!\n" % (
                             notification.merchantReference,
                             notification.reason))
    notification.confirmed = True
    notification.save()

def process_new_report(notification):
    # Just store the fact that this report is available. We'll have an
    # asynchronous cronjob that downloads and processes the reports.
    Report(notification=notification, url=notification.reason, processedat=None).save()
    notification.confirmed = True
    notification.save()


def process_one_notification(notification):
    # Now do notification specific processing
    if not notification.live:
        # This one is in the test system only! So we just send
        # an email, because we're lazy
        send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                         settings.ADYEN_NOTIFICATION_RECEIVER,
                         'Received adyen notification type %s from the test system!' % notification.eventCode,
                         "An Adyen notification with live set to false has been received.\nYou probably want to check that out manually - it's in the database, but has received no further processing.\n",
                         AdyenLog(pspReference=notification.pspReference, message='Received notification of type %s from the test system!' % notification.eventCode, error=True).save()
        )
        notification.confirmed = True
        notification.save()
    elif notification.eventCode == 'AUTHORISATION':
        process_authorization(notification)
    elif notification.eventCode == 'REPORT_AVAILABLE':
        process_new_report(notification)
    elif notification.eventCode == 'CAPTURE':
        process_capture(notification)
    elif notification.eventCode == 'REFUND':
        process_refund(notification)
    elif notification.eventCode in ('UNSPECIFIED', ):
        # Any events that we just ignore still need to be flagged as
        # confirmed
        notification.confirmed = True
        notification.save()
        AdyenLog(pspReference=notification.pspReference, message='Received notification of type %s, ignored' % notification.eventCode).save()
    else:
        # Received an event that needs manual processing because we
        # don't know what to do with it. To make sure we can react
        # quickly to this, generate an immediate email for this.
        send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                         settings.ADYEN_NOTIFICATION_RECEIVER,
                         'Received unknown Adyen notification of type %s' % notification.eventCode,
                         "An unknown Adyen notification of type %s has been received.\n\nYou'll need to go process this one manually:\n%s" % (
                             notification.eventCode,
                             reverse('admin:adyen_notification_change', args=(notification.id,)),
                         )
        )
        AdyenLog(pspReference=notification.pspReference, message='Received notification of unknown type %s' % notification.eventCode, error=True).save()

        # We specifically do *not* set the confirmed flag on this,
        # so that the cronjob will constantly bug the user about
        # unverified notifications.





def process_raw_adyen_notification(raw, POST):
    # Process a single raw Adyen notification. Must *not* be called in
    # a transactional context, as it manages it's own.

    # Now open a transaction for actually processing what we get
    with transaction.atomic():
        # Set it to confirmed - if we were unable to process the RAW one,
        # this will be rolled back by the transaction, and that's the only
        # thing that htis flag means. Anything else is handled by the
        # regular notification.
        raw.confirmed = True
        raw.save()

        # Have we already seen this notification before?
        notlist = list(Notification.objects.filter(pspReference=POST['pspReference'], eventCode=POST['eventCode'], merchantAccountCode=POST['merchantAccountCode']))
        if len(notlist) == 1:
            # Found it before!
            notification = notlist[0]

            # According to Adyen integration manual, the only case when
            # we need to process this is when it goes from
            # success=False -> success=True.
            if not notification.success and POST['success'] == 'true':
                # We'll implement this one later, but for now trigger a
                # manual email so we don't loose things.
                send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                                 settings.ADYEN_NOTIFICATION_RECEIVER,
                                 'Received adyen notification type %s that went from failure to success!' % notification.eventCode,
                                 "An Adyen notification that went from failure to success has been received.\nThe system doesn't know how to handle this yet, so you'll need to go take a manual look!\n",
                             )
                AdyenLog(pspReference=notification.pspReference, message='Received success->fail notification of type %s, unhandled' % notification.eventCode, error=True).save()
            else:
                AdyenLog(pspReference=notification.pspReference, message='Received duplicate %s notification' % notification.eventCode).save()
                # Don't actually do any processing here either
        else:
            # Not found, so create
            notification = Notification()
            notification.rawnotification = raw
            notification.eventDate = POST['eventDate']
            notification.eventCode = POST['eventCode']
            notification.live = (POST['live'] == 'true')
            notification.success = (POST['success'] == 'true')
            notification.pspReference = POST['pspReference']
            notification.originalReference = POST['originalReference']
            notification.merchantReference = POST['merchantReference']
            notification.merchantAccountCode = POST['merchantAccountCode']
            notification.paymentMethod = POST['paymentMethod']
            notification.reason = POST['reason']
            try:
                notification.amount = Decimal(POST['value']) / 100
            except:
                # Invalid amount, set to -1
                AdyenLog(pspReference=notification.pspReference, message='Received invalid amount %s' % POST['value'], error=True).save()
                notification.amount = -1
            if POST['currency'] != settings.CURRENCY_ABBREV:
                # For some reason, *report* notifications specifically get delivered with
                # a hard-coded value of EUR, even though they have no currency inside them.
                if notification.eventCode != 'REPORT_AVAILABLE':
                    AdyenLog(pspReference=notification.pspReference, message='Received invalid currency %s' % POST['currency'], error=True).save()
                    notification.amount = -2

            # Save this unconfirmed for now
            notification.save()

            # Process this notification, which includes flagging invoices
            # as paid.
            process_one_notification(notification)

            # Log the fact that we received it
            AdyenLog(pspReference=notification.pspReference, message='Processed %s notification for %s' % (notification.eventCode, notification.merchantReference)).save()

    # Return that we've consumed the report outside the transaction, in
    # the unlikely event that the COMMIT is what failed
    return True



#
# Accesspoints into the Adyen API
#
# Most of the API is off limits to us due to lack of PCI, but we can do a couple
# of important things like refunding.
#

class AdyenAPI(object):
    def refund_transaction(self, refundid, transreference, amount):
        apiparam = {
            'merchantAccount': settings.ADYEN_MERCHANTACCOUNT,
            'modificationAmount': {
                'value': int(amount * 100), # "minor units", so cents!
                'currency': settings.CURRENCY_ISO,
            },
            'originalReference': transreference,
            'reference': '{0}{1}'.format(settings.ADYEN_MERCHANTREF_REFUND_PREFIX, refundid),
        }

        try:
            r = self._api_call('pal/servlet/Payment/v12/refund', apiparam, '[refund-received]')
            return r['pspReference']
        except Exception, e:
            raise Exception("API call to refund transaction {0} (refund {1}) failed: {2}".format(
                transreference,
                refundid,
                e))


    def _api_call(self, apiurl, apiparam, okresponse):
        apijson = json.dumps(apiparam)

        req = urllib2.Request("{0}{1}".format(settings.ADYEN_APIBASEURL, apiurl))

        req.add_header('Authorization', 'Basic {0}'.format(
            standard_b64encode('{0}:{1}'.format(settings.ADYEN_WS_USER, settings.ADYEN_WS_PASSWORD))))
        req.add_header('Content-type', 'application/json')
        u = urllib2.urlopen(req, apijson)
        resp = u.read()
        if u.getcode() != 200:
            raise Exception("http response code {0}".format(u.getcode()))
        u.close()
        r = json.loads(resp)

        if r['response'] != okresponse:
            raise Exception("response returned: {0}".format(r['response']))

        return r
