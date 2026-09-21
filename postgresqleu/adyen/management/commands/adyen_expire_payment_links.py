# Expire payment links on the Adyen platform that have expired
#
#
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

import datetime
import time

from postgresqleu.adyen.models import AdyenInvoicePaymentLink, AdyenLog

import requests


class Command(BaseCommand):
    help = 'Expire Adyen payment links'

    class ScheduledJob:
        scheduled_times = [datetime.time(22, 10), ]
        internal = True

        @classmethod
        def should_run(self):
            return AdyenInvoicePaymentLink.objects.filter(expires__lt=timezone.now()).exists()

    def handle(self, *args, **options):
        now = timezone.now()
        for link in AdyenInvoicePaymentLink.objects.filter(expires__lt=now, forceexpire=True):
            pm = link.paymentmethod.get_implementation()

            with transaction.atomic():
                r = requests.request(
                    'PATCH',
                    '{}/v68/paymentLinks/{}'.format(pm.config('checkoutbaseurl').rstrip('/'), link.linkid),
                    json={
                        "status": "expired",
                    },
                    headers={
                        'x-api-key': pm.config('ws_apikey'),
                    },
                    timeout=10,
                )
                if r.status_code != 200:
                    AdyenLog(pspReference='', message='Unable to force-expire payment link {}: {}'.format(link.linkid, r.text))
                else:
                    AdyenLog(pspReference='', message='Payment link {} forcibly expired'.format(link.linkid), paymentmethod=link.paymentmethod).save()
                    link.delete()
                # Add a small delay to not get flood-flagged
                time.sleep(2)

        # Clean up payment links already expired
        AdyenInvoicePaymentLink.objects.filter(expires__lt=now).delete()
