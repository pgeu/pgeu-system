from django.conf import settings
from django.db import transaction

from datetime import datetime, timedelta
from decimal import Decimal

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod

from .api import TrustlyWrapper, TrustlyException
from .models import TrustlyTransaction, TrustlyLog
from .models import TrustlyNotification


# Django intgrated wrapper for the trustly API
class Trustly(TrustlyWrapper):
    def __init__(self, pm):
        self.pm = pm
        super(Trustly, self).__init__(pm.get_apibase(),
                                      pm.config('user'),
                                      pm.config('password'),
                                      pm.config('private_key'),
                                      pm.config('public_key'),
                                      '{0}/trustly_notification/{1}/'.format(settings.SITEBASE, pm.id),
                                      settings.CURRENCY_ABBREV,
                                      pm.config('hold_notifications', False),
                                      )

    def process_raw_trustly_notification(self, raw):
        (uuid, method, data) = self.parse_notification(raw.contents)
        if not data:
            TrustlyLog(message="Failed to parse trustly raw notification {0}".format(raw.id),
                       error=True,
                       paymentmethod=raw.paymentmethod).save()
            return (False, uuid, method)

        n = None
        with transaction.atomic():
            # Find if we have already seen this guy
            try:
                TrustlyNotification.objects.get(notificationid=data['notificationid'])
                # If it's found, then we're happy, so keep on smiling. Flag this one as
                # confirmed as well.
                raw.confirmed = True
                raw.save()
                return (True, uuid, method)
            except TrustlyNotification.DoesNotExist:
                pass

            n = TrustlyNotification(
                receivedat=datetime.now(),
                rawnotification=raw,
                method=method,
                notificationid=data['notificationid'],
                orderid=data['orderid'],
                amount='amount' in data and Decimal(data['amount']) or None,
                messageid=data['messageid'],
            )
            n.save()
            raw.confirmed = True
            raw.save()

        # Raw is confirmed, but parsed one is still pending. So handle that one.
        try:
            self.process_notification(n)
        except Exception as e:
            self.log_and_email("Exception processing notification {0}: {1}".format(n.id, e), raw.paymentmethod)

        # If we somehow failed to handle at this level, we still flag things as ok to
        # Trustly, and deal with it ourselves.
        # Notifications can always be re-parsed
        return (True, uuid, method)

    def log_and_email(self, message, paymentmethod):
        TrustlyLog(message=message, error=True, paymentmethod=paymentmethod).save()

        send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                         self.pm.config('notification_receiver'),
                         "Trustly payment error",
                         "A trustly payment for {0} failed with the error:\n\n{1}".format(paymentmethod.internaldescription, message),
                         )

    @transaction.atomic
    def process_notification(self, notification):
        method = notification.rawnotification.paymentmethod
        if notification.method in ('pending', 'credit'):
            # Find the appropriate transaction
            try:
                trans = TrustlyTransaction.objects.get(orderid=notification.orderid, paymentmethod=method)
            except TrustlyTransaction.DoesNotExist:
                self.log_and_email("Transaction {0} for notification {1} not found!".format(notification.orderid, notification.id), method)
                return False
            if trans.amount != notification.amount:
                self.log_and_email("Notification {0} for transaction {1} has invalid amount ({2} should be {3})!".format(notification.id, notification.orderid, notification.amount, trans.amount), method)
                return False

            if notification.method == 'pending':
                # Pending is just an incremental state, so we collect it but don't do anything with
                # it.
                if not trans.pendingat:
                    trans.pendingat = datetime.now()
                    trans.save()

                try:
                    self.process_pending_payment(trans)
                except TrustlyException as e:
                    self.log_and_email(e, method)
                    return False

                notification.confirmed = True
                notification.save()

                TrustlyLog(message="Pending payment for Trustly id {0} (order {1}) received".format(trans.id, trans.orderid), paymentmethod=method).save()

                return True
            else:
                # Credit! The payment is completed!
                if not trans.pendingat:
                    # We set pending in case it never showed up
                    trans.pendingat = datetime.now()
                if trans.completedat:
                    self.log_and_email("Duplicate completed notification ({0}) received for transaction {1}!".format(notification.id, notification.orderid), method)
                    return False

                trans.completedat = datetime.now()
                try:
                    self.process_completed_payment(trans)
                except TrustlyException as e:
                    self.log_and_email(e, method)
                    return False
                trans.save()
                notification.confirmed = True
                notification.save()
                return True
        elif notification.method == 'cancel':
            try:
                trans = TrustlyTransaction.objects.get(orderid=notification.orderid, paymentmethod=method)
                if trans.pendingat:
                    self.log_and_email("Transaction {0} canceled by notification {1} but already in progress. Ignoring cancel!".format(notification.orderid, notification.id), method)
                    return False
                TrustlyLog(message='Transaction {0} canceled from notification'.format(notification.orderid), paymentmethod=method).save()
                trans.delete()
            except TrustlyTransaction.DoesNotExist:
                TrustlyLog("Abandoned transaction {0} canceled from notification".format(notification.orderid), paymentmethod=method)
            notification.confirmed = True
            notification.save()
            return True
        else:
            self.log_and_email("Unknown notification type '{0}' in notification {1}".format(notification.method, notification.id), method)
            return False

        # Can't reach here
        return False

    def get_invoice_for_transaction(self, trans):
        try:
            return Invoice.objects.get(pk=trans.invoiceid)
        except Invoice.DoesNotExist:
            raise TrustlyException("Received Trustly notification for non-existing invoice id {0}".format(trans.invoiceid))

    def process_pending_payment(self, trans):
        # If we have received a 'pending' notification, postpone the invoice to ensure it's valid
        # for another 2 hours, in case the credit notification is slightly delayed.
        # A cronjob will run every hour to potentially further extend this.
        manager = InvoiceManager()
        invoice = self.get_invoice_for_transaction(trans)

        # Postpone the invoice so it's valid for at least another 2 hours.
        r = manager.postpone_invoice_autocancel(invoice,
                                                timedelta(hours=2),
                                                reason="Trustly pending arrived, awaiting credit",
                                                silent=True)
        if r:
            TrustlyLog(message="Extended autocancel time for invoice {0} to ensure time for credit notification".format(invoice.id),
                       paymentmethod=trans.paymentmethod).save()

    def process_completed_payment(self, trans):
        manager = InvoiceManager()
        invoice = self.get_invoice_for_transaction(trans)

        def invoice_logger(msg):
            raise TrustlyException("Trustly invoice processing failed: {0}".format(msg))

        method = trans.paymentmethod
        pm = method.get_implementation()

        manager.process_incoming_payment_for_invoice(invoice,
                                                     trans.amount,
                                                     'Trustly id {0}'.format(trans.id),
                                                     0,  # XXX: we pay zero now, but should perhaps support fees?
                                                     pm.config('accounting_income'),
                                                     pm.config('accounting_fee'),
                                                     [],
                                                     invoice_logger,
                                                     method)

        TrustlyLog(message="Completed payment for Trustly id {0} (order {1}), {2}{3}, invoice {4}".format(trans.id, trans.orderid, settings.CURRENCY_ABBREV, trans.amount, invoice.id), paymentmethod=method).save()

        send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                         pm.config('notification_receiver'),
                         "Trustly payment completed",
                         "A Trustly payment for {0} of {1}{2} for invoice {3} was completed on the Trustly platform.\n\nInvoice: {4}\nRecipient name: {5}\nRecipient email: {6}\n".format(
                             method.internaldescription,
                             settings.CURRENCY_ABBREV,
                             trans.amount,
                             invoice.id,
                             invoice.title,
                             invoice.recipient_name,
                             invoice.recipient_email),
                         )
