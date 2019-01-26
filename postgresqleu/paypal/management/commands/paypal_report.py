#
# This script sends out reports of activity and errors in the paypal
# integration, as well as a list of any unmatched payments still in
# the system.
#
# Copyright (C) 2010-2018, PostgreSQL Europe
#

from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from datetime import time

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.paypal.models import ErrorLog, TransactionInfo
from postgresqleu.mailqueue.util import send_simple_mail


class Command(BaseCommand):
    help = 'Send paypal reports'

    class ScheduledJob:
        scheduled_times = [time(1, 15), ]
        internal = True

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.paypal.Paypal').exists()

    @transaction.atomic
    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.paypal.Paypal'):
            self.report_for_method(method)

    def report_for_method(self, method):
        pm = method.get_implementation()

        entries = ErrorLog.objects.filter(sent=False, paymentmethod=method).order_by('id')
        if len(entries):
            msg = """
Events reported by the paypal integration for {0}:

{1}
""".format(
                method.internaldescription,
                "\n".join(["{0}: {1}".format(e.timestamp, e.message) for e in entries]),
            )

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('report_receiver'),
                             'Paypal Integration Report',
                             msg)
            entries.update(sent=True)

        entries = TransactionInfo.objects.filter(matched=False).order_by('timestamp')
        if len(entries):
            msg = """
The following payments have been received but not matched to anything in
the system for {0}:

{1}

These will keep being reported until there is a match found or they are
manually dealt with in the admin interface!
""".format(
                method.internaldescription,
                "\n".join(["{0}: {1} ({2}) sent {3} with text '{4}'".format(e.timestamp, e.sender, e.sendername, e.amount, e.transtext) for e in entries])
            )

            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('report_receiver'),
                             'Paypal Unmatched Transactions',
                             msg)
