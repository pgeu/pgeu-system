#
# This script updates pending Stripe transactions, in the event
# the webhook has not been sent or not been properly processed.
#

from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from datetime import time, datetime, timedelta

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.stripepayment.models import StripeCheckout
from postgresqleu.stripepayment.util import process_stripe_checkout


class Command(BaseCommand):
    help = 'Update Stripe transactions'

    class ScheduledJob:
        scheduled_interval = timedelta(hours=4)

        @classmethod
        def should_run(self):
            if InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.stripe.Stripe').exists():
                return StripeCheckout.objects.filter(completedat__isnull=True).exists()

    def handle(self, *args, **options):
        for co in StripeCheckout.objects.filter(completedat__isnull=True):
            process_stripe_checkout(co)
