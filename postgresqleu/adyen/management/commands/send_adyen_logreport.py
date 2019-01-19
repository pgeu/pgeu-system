# This script sends out reports of errors in the Adyen integration as
# a summary email.
#
# Copyright (C) 2013, PostgreSQL Europe
#
from django.core.management.base import BaseCommand
from django.db import transaction
from django.urls import reverse
from django.conf import settings

from datetime import datetime, timedelta
from io import StringIO

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.adyen.models import AdyenLog, Notification, TransactionStatus
from postgresqleu.mailqueue.util import send_simple_mail


class Command(BaseCommand):
    help = 'Send log information about Adyen events'

    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname__in=(['postgresqleu.util.payment.adyen.AdyenCreditcard', 'postgresqleu.util.payment.adyen.AdyenBanktransfer'])):
            pm = method.get_implementation()

            self.report_loglines(method, pm)
            self.report_unconfirmed_notifications(method, pm)
            self.report_unsettled_transactions(method, pm)

    @transaction.atomic
    def report_loglines(self, method, pm):
        lines = list(AdyenLog.objects.filter(error=True, sent=False, paymentmethod=method).order_by('timestamp'))
        if len(lines):
            sio = StringIO()
            sio.write("The following error events have been logged by the Adyen integration for %s:\n\n" % method.internaldescription)
            for l in lines:
                sio.write("%s: %20s: %s\n" % (l.timestamp, l.pspReference, l.message))
                l.sent = True
                l.save()
            sio.write("\n\n\nAll these events have now been tagged as sent, and will no longer be\nprocessed by the system in any way.\n")

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Adyen integration error report',
                             sio.getvalue())

    def report_unconfirmed_notifications(self, method, pm):
        lines = list(Notification.objects.filter(confirmed=False, receivedat__lt=datetime.now() - timedelta(days=1), rawnotification__paymentmethod=method).order_by('eventDate'))
        if len(lines):
            sio = StringIO()
            sio.write("The following notifications have not been confirmed in the Adyen integration for %s.\nThese need to be manually processed and then flagged as confirmed!\n\nThis list only contains unconfirmed events older than 24 hours.\n\n\n" % method.internaldescription)
            for l in lines:
                sio.write("%s: %s (%s%s)\n" % (l.eventDate, l.eventCode, settings.SITEBASE, reverse('admin:adyen_notification_change', args=(l.id,))))

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Adyen integration unconfirmed notifications',
                             sio.getvalue())

    def report_unsettled_transactions(self, method, pm):
        # Number of days until we start reporting unsettled transactions

        UNSETTLED_THRESHOLD = 15
        lines = list(TransactionStatus.objects.filter(settledat__isnull=True, authorizedat__lt=datetime.now() - timedelta(days=UNSETTLED_THRESHOLD), paymentmethod=method).order_by('authorizedat'))
        if len(lines):
            sio = StringIO()
            sio.write("The following payments have been authorized for %s, but not captured for more than %s days.\nThese probably need to be verified manually.\n\n\n" % (method.internaldescription, UNSETTLED_THRESHOLD))

            for l in lines:
                sio.write("%s at %s: %s (%s%s)\n" % (l.pspReference, l.authorizedat, l.amount, settings.SITEBASE, reverse('admin:adyen_transactionstatus_change', args=(l.id,))))

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Adyen integration unconfirmed notifications',
                             sio.getvalue())
