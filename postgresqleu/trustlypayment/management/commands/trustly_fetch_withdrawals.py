#
# This script tracks withdrawals from Trustly into main bank account.
#
# Copyright (C) 2019 PostgreSQL Europe
#


from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from datetime import datetime, timedelta
from decimal import Decimal

from postgresqleu.accounting.util import create_accounting_entry
from postgresqleu.invoices.util import is_managed_bank_account
from postgresqleu.invoices.util import register_pending_bank_matcher

from postgresqleu.invoices.models import InvoicePaymentMethod, Invoice
from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.trustlypayment.util import Trustly
from postgresqleu.trustlypayment.models import TrustlyWithdrawal, TrustlyLog, TrustlyTransaction


class Command(BaseCommand):
    help = 'Fetch Trustly withdrawals/refunds'

    class ScheduledJob:
        scheduled_interval = timedelta(hours=6)

        @classmethod
        def should_run(self):
            return InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.trustly.TrustlyPayment').exists()

    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.trustly.TrustlyPayment'):
            self.fetch_one_account(method)

    @transaction.atomic
    def fetch_one_account(self, method):
        pm = method.get_implementation()

        trustly = Trustly(pm)

        transactions = trustly.getledgerforrange(datetime.today() - timedelta(days=7), datetime.today())

        for t in transactions:
            if t['accountname'] == 'BANK_WITHDRAWAL_QUEUED':
                if t['currency'] != settings.CURRENCY_ABBREV:
                    TrustlyLog(
                        message="Received Trustly withdrawal with gluepayid {} in currency {}, expected {}.".format(
                            t['gluepayid'], t['currency'], settings.CURRENCY_ABBREV,
                        ),
                        error=True,
                        paymentmethod=method,
                    ).save()
                    continue

                w, created = TrustlyWithdrawal.objects.get_or_create(paymentmethod=method,
                                                                     gluepayid=t['gluepayid'],
                                                                     defaults={
                                                                         'amount': -Decimal(t['amount']),
                                                                         'message': t['messageid'],
                                                                         'orderid': t['orderid'],
                                                                     },
                )
                w.save()

                if created:
                    TrustlyLog(message='New bank withdrawal of {0} found'.format(-Decimal(t['amount'])),
                               paymentmethod=method).save()

                    if w.orderid:
                        # This is either a payout (which we don't support) or a refund (which we do, so track it here)
                        if not w.message.startswith('Refund '):
                            TrustlyLog(
                                message="Received bank withdrawal with orderid {} that does not appear to be a refund. What is it?".format(w.orderid),
                                error=True,
                                paymentmethod=method,
                            ).save()
                            continue

                        try:
                            trans = TrustlyTransaction.objects.get(orderid=t['orderid'])
                        except TrustlyTransaction.DoesNotExist:
                            TrustlyLog(
                                message="Received bank withdrawal with orderid {} which does not exist!".format(w.orderid),
                                error=True,
                                paymentmethod=method,
                            ).save()
                            continue

                        # Do we have a matching refund object?
                        refundlist = list(Invoice.objects.get(pk=trans.invoiceid).invoicerefund_set.filter(issued__isnull=False, completed__isnull=True))
                        for r in refundlist:
                            if r.fullamount == w.amount:
                                # Found the matching refund!
                                manager = InvoiceManager()
                                manager.complete_refund(
                                    r.id,
                                    r.fullamount,
                                    0,
                                    pm.config('accounting_income'),
                                    pm.config('accounting_fee'),
                                    [],
                                    method,
                                )
                                w.matched_refund = r
                                w.save(update_fields=['matched_refund'])
                                break
                        else:
                            # Another option is it's a refund in a different currency and we lost out on some currency conversion.
                            # If we find a refund that's within 5% of the original value and we didn't find an exact one, then let's assume that's the case.
                            # (in 99.999% of all cases there will only be one refund pending, so it'll very likely be correct)
                            for r in refundlist:
                                if w.amount < r.fullamount and w.amount / r.fullamount > 0.95:
                                    manager = InvoiceManager()
                                    manager.complete_refund(
                                        r.id,
                                        r.fullamount,
                                        r.fullamount - w.amount,
                                        pm.config('accounting_income'),
                                        pm.config('accounting_fee'),
                                        [],
                                        method,
                                    )
                                    w.matched_refund = r
                                    w.save(update_fields=['matched_refund'])
                                    TrustlyLog(
                                        message="Refund for order {}, invoice {}, was made as {} {}. Found no exact match for a refund, but matched to a refund of {} {} with fees of {} {}. Double check!".format(
                                            w.orderid, r.invoice_id,
                                            w.amount, settings.CURRENCY_ABBREV,
                                            r.fullamount, settings.CURRENCY_ABBREV,
                                            r.fullamount - w.amount, settings.CURRENCY_ABBREV,
                                        ),
                                        error=False,
                                        paymentmethod=method,
                                    ).save()
                                    break
                            else:
                                TrustlyLog(
                                    message="Received refund of {} for orderid {}, but could not find a matching refund object.".format(w.amount, w.orderid),
                                    error=True,
                                    paymentmethod=method,
                                ).save()
                    else:
                        # No orderid means it's a payout/settlement
                        accstr = 'Transfer from Trustly to bank'
                        accrows = [
                            (pm.config('accounting_income'), accstr, -w.amount, None),
                            (pm.config('accounting_transfer'), accstr, w.amount, None),
                        ]
                        entry = create_accounting_entry(accrows,
                                                        True,
                                                        [],
                        )
                        if is_managed_bank_account(pm.config('accounting_transfer')):
                            register_pending_bank_matcher(pm.config('accounting_transfer'),
                                                          '.*TRUSTLY.*{0}.*'.format(w.gluepayid),
                                                          w.amount,
                                                          entry)
