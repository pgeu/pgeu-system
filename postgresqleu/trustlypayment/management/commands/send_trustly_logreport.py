# This script sends out reports of errors in the Trustly integration as
# a summary email.
#
# Copyright (C) 2016, PostgreSQL Europe
#
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from datetime import datetime, timedelta, time
from io import StringIO

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.trustlypayment.models import TrustlyLog, TrustlyNotification, TrustlyTransaction
from postgresqleu.mailqueue.util import send_simple_mail


class Command(BaseCommand):
    help = 'Send log information about Trustly events'

    class ScheduledJob:
        scheduled_times = [time(23, 15), ]
        internal = True

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.trustly.TrustlyPayment').exists()

    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.trustly.TrustlyPayment'):
            pm = method.get_implementation()
            self.report_loglines(method, pm)
            self.report_unconfirmed_notifications(method, pm)
            self.report_unfinished_transactions(method, pm)

    @transaction.atomic
    def report_loglines(self, method, pm):
        lines = list(TrustlyLog.objects.filter(error=True, sent=False, paymentmethod=method).order_by('timestamp'))
        if len(lines):
            sio = StringIO()
            sio.write("The following error events have been logged by the Trustly integration for {0}:\n\n".format(method.internaldescription))
            for l in lines:
                sio.write("%s: %s\n" % (l.timestamp, l.message))
                l.sent = True
                l.save()
            sio.write("\n\n\nAll these events have now been tagged as sent, and will no longer be\nprocessed by the system in any way.\n")

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Trustly integration error report',
                             sio.getvalue())

    def report_unconfirmed_notifications(self, method, pm):
        lines = list(TrustlyNotification.objects.filter(confirmed=False, receivedat__lt=datetime.now() - timedelta(days=1), rawnotification__paymentmethod=method).order_by('receivedat'))
        if len(lines):
            sio = StringIO()
            sio.write("The following notifications have not been confirmed in the Trustly integration for {0}.\nThese need to be manually processed and then flagged as confirmed!\n\nThis list only contains unconfirmed events older than 24 hours.\n\n\n".format(method.internaldescription))
            for l in lines:
                sio.write("%s: %s\n" % (l.receivedat, l.method, ))

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Trustly integration unconfirmed notifications',
                             sio.getvalue())

    def report_unfinished_transactions(self, method, pm):
        # Number of days until we start reporting unfinished transactions
        # Note: we only care about transactions that have actually started, where the user
        # got the first step of confirmation. The ones that were never started are uninteresting.
        UNFINISHED_THRESHOLD = 3

        lines = list(TrustlyTransaction.objects.filter(completedat__isnull=True, pendingat__isnull=False, pendingat__lt=datetime.now() - timedelta(days=UNFINISHED_THRESHOLD), paymentmethod=method).order_by('pendingat'))
        if len(lines):
            sio = StringIO()
            sio.write("The following payments have been authorized for %s, but not finished for more than %s days.\nThese probably need to be verified manually.\n\n\n" % (method.internaldescription, UNFINISHED_THRESHOLD))

            for l in lines:
                sio.write("%s at %s: %s\n" % (l.orderid, l.pendingat, l.amount))

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Trustly integration unconfirmed notifications',
                             sio.getvalue())
