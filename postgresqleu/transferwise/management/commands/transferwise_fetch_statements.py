#
# This script fetches monthly statements in PDF format from transferwise
# and passes them on to the notification address.
#
# Copyright (C) 2019, PostgreSQL Europe
#


from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from django.conf import settings

import datetime

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.transferwise.models import TransferwiseMonthlyStatement


class Command(BaseCommand):
    help = 'Fetch TransferWise monthly statements'

    class ScheduledJob:
        scheduled_times = [datetime.time(2, 2), ]

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.transferwise.Transferwise').exists()

    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.transferwise.Transferwise'):
            self.fetch_one_statement(method)

    @transaction.atomic
    def fetch_one_statement(self, method):
        pm = method.get_implementation()
        if not pm.config('send_statements'):
            return

        # We fetch for the *previous* month. Take todays day, truncate it to the month,
        # subtract one day to get the last day of the previous month, and then truncate
        # again to the first of that month.
        d = (datetime.date.today().replace(day=1) - datetime.timedelta(days=1)).replace(day=1)

        if TransferwiseMonthlyStatement.objects.filter(paymentmethod=method, month=d).exists():
            return

        # Else we don't have it, so download it
        api = pm.get_api()
        r = api.get_binary('borderless-accounts/{0}/statement.pdf'.format(api.get_account()['id']), {
            'currency': settings.CURRENCY_ABBREV,
            'intervalStart': api.format_date(d),
            'intervalEnd': api.format_date(datetime.date.today().replace(day=1)),

        })
        statement = TransferwiseMonthlyStatement(
            paymentmethod=method,
            month=d,
            contents=r.read(),
        )
        statement.save()

        send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                         pm.config('notification_receiver'),
                         'TransferWise monthly statement for {}'.format(statement.month.strftime("%B %Y")),
                         "The TransferWise monthly statement for {0} for the month of {1} is attached.".format(
                             method.internaldescription,
                             statement.month.strftime("%B %Y"),
                         ),
                         attachments=[
                             ('TransferWise_{}.pdf'.format(statement.month.strftime("%b_%Y")), 'application/pdf', statement.contents),
                         ]
        )
