from django.conf import settings
from django.db import transaction

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.invoices.models import Invoice

from .models import StripeLog
from .api import StripeApi, StripeException


def process_stripe_checkout(co):
    if co.completedat:
        # Already completed, so don't do anything with it
        return

    with transaction.atomic():
        method = co.paymentmethod
        pm = method.get_implementation()
        api = StripeApi(pm)

        # Update the status from the API
        if api.update_checkout_status(co):
            # Went from unpaid to paid, so Do The Magic (TM)
            manager = InvoiceManager()
            invoice = Invoice.objects.get(pk=co.invoiceid)

            def invoice_logger(msg):
                raise StripeException("Stripe invoice processing failed: {0}".format(msg))

            manager.process_incoming_payment_for_invoice(invoice,
                                                         co.amount,
                                                         'Stripe checkout id {0}'.format(co.id),
                                                         co.fee,
                                                         pm.config('accounting_income'),
                                                         pm.config('accounting_fee'),
                                                         [],
                                                         invoice_logger,
                                                         method)

            StripeLog(message="Completed payment for Stripe id {0} ({1}{2}, invoice {3})".format(co.id, settings.CURRENCY_ABBREV, co.amount, invoice.id), paymentmethod=method).save()

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             "Stripe payment completed",
                             "A Stripe payment for {0} of {1}{2} for invoice {3} was completed.\n\nInvoice: {4}\nRecipient name: {5}\nRecipient email: {6}\n".format(
                                 method.internaldescription,
                                 settings.CURRENCY_ABBREV,
                                 co.amount,
                                 invoice.id,
                                 invoice.title,
                                 invoice.recipient_name,
                                 invoice.recipient_email,
                             )
            )
