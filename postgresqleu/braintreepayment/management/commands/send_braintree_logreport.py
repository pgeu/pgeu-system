# This script sends out reports fo errors in the Braintree integration
# as a summary email.
#
# Copyright (C) 2015-2019, PostgreSQL Europe
#
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from datetime import time
from io import StringIO

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.braintreepayment.models import BraintreeLog
from postgresqleu.mailqueue.util import send_simple_mail


class Command(BaseCommand):
    help = 'Send log information about Braintree events'

    class ScheduledJob:
        scheduled_times = [time(23, 32), ]
        internal = True

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.braintree.Braintree').exists()

    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.braintree.Braintree'):
            self.send_for_method(method)

    @transaction.atomic
    def send_for_method(self, method):
        pm = method.get_implementation()
        lines = list(BraintreeLog.objects.filter(error=True, sent=False, paymentmethod=method).order_by('timestamp'))

        if len(lines):
            sio = StringIO()
            sio.write("The following error events have been logged by the Braintree integration:\n\n")
            for l in lines:
                sio.write("%s: %20s: %s\n" % (l.timestamp, l.transid, l.message))
                l.sent = True
                l.save()
            sio.write("\n\n\nAll these events have now been tagged as sent, and will no longer be\nprocessed by the system in any way.\n")

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Braintree integration error report',
                             sio.getvalue())
