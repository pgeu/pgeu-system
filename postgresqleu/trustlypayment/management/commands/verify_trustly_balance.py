#
# This script compares the balance of the trustly account with the
# one in the accounting system, raising an alert if they are different
# (which indicates that something has been incorrectly processed).
#
# Copyright (C) 2010-2016, PostgreSQL Europe
#


from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.trustlypayment.util import Trustly
from postgresqleu.accounting.util import get_latest_account_balance
from postgresqleu.mailqueue.util import send_simple_mail


class Command(BaseCommand):
    help = 'Compare trustly balance to the accounting system'

    @transaction.atomic
    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.trustly.TrustlyPayment'):
            self.verify_one_account(method)

    def verify_one_account(self, method):
        method = method
        pm = method.get_implementation()

        trustly = Trustly(pm)

        trustly_balance = trustly.get_balance()

        accounting_balance = get_latest_account_balance(pm.config('accounting_income'))

        if accounting_balance != trustly_balance:
            send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                             pm.config('notification_receiver'),
                             'Trustly balance mismatch!',
                             """Trustly balance ({0}) for {1} does not match the accounting system ({2})!

This could be because some entry has been missed in the accouting
(automatic or manual), or because of an ongoing booking of something
that the system deosn't know about.

Better go check manually!
""".format(trustly_balance, method.internaldescription, accounting_balance))
