# Set up all available payment providers
#
# Copyright (C) 2016, PostgreSQL Europe
#

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, connection

from postgresqleu.invoices.models import InvoicePaymentMethod


class Command(BaseCommand):
    help = 'Set up payment providers'

    @transaction.atomic
    def handle(self, *args, **options):
        # Handle old names if they are there
        curs = connection.cursor()
        curs.execute("UPDATE invoices_invoicepaymentmethod SET classname='postgresqleu.'||classname WHERE classname LIKE 'util.payment%' RETURNING classname")
        for c, in curs.fetchall():
            self.stdout.write("Updated classname for {0}.".format(self.style.WARNING(c)))

        # Create the ones that don't exist if any
        (p, created) = InvoicePaymentMethod.objects.get_or_create(classname='postgresqleu.util.payment.paypal.Paypal', defaults={'name': 'Paypal or credit card', 'sortkey': 100, 'auto': False, 'internaldescription': 'Paypal', 'active': False})
        if created:
            self.stdout.write("Created payment method Paypal ({0})".format(self.style.WARNING("disabled")))

        (p, created) = InvoicePaymentMethod.objects.get_or_create(classname='postgresqleu.util.payment.banktransfer.Banktransfer', defaults={'name': 'Bank transfer', 'sortkey': 200, 'auto': False, 'internaldescription': 'Manual bank transfer', 'active': False})
        if created:
            self.stdout.write("Created payment method Manual bank transfer ({0})".format(self.style.WARNING("disabled")))

        (p, created) = InvoicePaymentMethod.objects.get_or_create(classname='postgresqleu.util.payment.adyen.AdyenCreditcard', defaults={'name': 'Credit card', 'sortkey': 50, 'auto': False, 'internaldescription': 'Adyen creditcard', 'active': False})
        if created:
            self.stdout.write("Created payment method Adyen creditcard ({0})".format(self.style.WARNING("disabled")))

        (p, created) = InvoicePaymentMethod.objects.get_or_create(classname='postgresqleu.util.payment.adyen.AdyenBanktransfer', defaults={'name': 'Direct bank transfer', 'sortkey': 75, 'auto': False, 'internaldescription': 'Adyen managed bank transfer', 'active': False})
        if created:
            self.stdout.write("Created payment method Adyen bank transfer ({0})".format(self.style.WARNING("disabled")))

        (p, created) = InvoicePaymentMethod.objects.get_or_create(classname='postgresqleu.util.payment.dummy.DummyPayment', defaults={'name': 'Dummy', 'sortkey': 999, 'auto': False, 'active': False})
        if created:
            self.stdout.write("Created payment method Dummy ({0})".format(self.style.WARNING("disabled")))

        (p, created) = InvoicePaymentMethod.objects.get_or_create(classname='postgresqleu.util.payment.braintree.Braintree', defaults={'name': 'Credit card', 'sortkey': 51, 'auto': False, 'internaldescription': 'Braintree managed creditcard', 'active': False})
        if created:
            self.stdout.write("Created payment method Braintree creditcard ({0})".format(self.style.WARNING("disabled")))

        (p, created) = InvoicePaymentMethod.objects.get_or_create(classname='postgresqleu.util.payment.trustly.TrustlyPayment', defaults={'name': 'Bank payment using Trustly', 'sortkey': 60, 'auto': False, 'internaldescription': 'Trustly managed bank transfer', 'active': False})
        if created:
            self.stdout.write("Created payment method Trustly bank transfer ({0})".format(self.style.WARNING("disabled")))
