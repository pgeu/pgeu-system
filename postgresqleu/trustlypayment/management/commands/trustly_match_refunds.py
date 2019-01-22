#
# Trustly does not send notifications on refunds completed (they just
# give success as response to API call). For this reason, we have this
# script that polls to check if a refund has completed successfully.
#
# Copyright (C) 2010-2018, PostgreSQL Europe
#


from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

from postgresqleu.trustlypayment.util import Trustly
from postgresqleu.trustlypayment.models import TrustlyTransaction, TrustlyLog
from postgresqleu.invoices.models import InvoiceRefund, InvoicePaymentMethod
from postgresqleu.invoices.util import InvoiceManager

from decimal import Decimal
import dateutil


class Command(BaseCommand):
    help = 'Verify that a Trustly refund has completed, and flag it as such'

    @transaction.atomic
    def handle(self, *args, **options):
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.trustly.TrustlyPayment'):
            self.process_one_account(method)

    def process_one_account(self, method):
        pm = method.get_implementation()

        trustly = Trustly(pm)
        manager = InvoiceManager()

        refunds = InvoiceRefund.objects.filter(completed__isnull=True, invoice__paidusing=method)

        for r in refunds:
            # Find the matching Trustly transaction
            trustlytransactionlist = list(TrustlyTransaction.objects.filter(invoiceid=r.invoice.pk, paymentmethod=method))
            if len(trustlytransactionlist) == 0:
                raise CommandError("Could not find trustly transaction for invoice {0}".format(r.invoice.pk))
            elif len(trustlytransactionlist) != 1:
                raise CommandError("Found {0} trustly transactions for invoice {1}!".format(len(trustlytransactionlist), r.invoice.pk))
            trustlytrans = trustlytransactionlist[0]
            w = trustly.getwithdrawal(trustlytrans.orderid)
            if not w:
                # No refund yet
                continue

            if w['transferstate'] != 'CONFIRMED':
                # Still pending
                continue

            if w['currency'] != settings.CURRENCY_ABBREV:
                # If somebody paid in a different currency (and Trustly converted it for us),
                # the withdrawal entry is specified in the original currency, which is more than
                # a little annoying. To deal with it, attempt to fetch the ledger for the day
                # and if we can find it there, use the amount from that one.
                day = dateutil.parser.parse(w['datestamp']).date()
                ledgerrows = trustly.getledgerforday(day)
                for lr in ledgerrows:
                    if int(lr['orderid']) == trustlytrans.orderid and lr['accountname'] == 'BANK_WITHDRAWAL_QUEUED':
                        # We found the corresponding accounting row. So we take the amount from
                        # this and convert the difference to what we expeced into the fee. This
                        # can end up being a negative fee, but it should be small enough that
                        # it's not a real problem.
                        fees = (-Decimal(lr['amount']) - r.fullamount).quantize(Decimal('0.01'))
                        TrustlyLog(
                            message="Refund for order {0}, invoice {1}, was made as {2} {3} instead of {4} {5}. Using ledger mapped to {6} {7} with difference of {8} {9} booked as fees".format(
                                trustlytrans.orderid,
                                r.invoice.pk,
                                Decimal(r['amount']),
                                w['currency'],
                                r.fullamount,
                                settings.CURRENCY_ABBREV,
                                Decimal(lr['amount']).quantize(Decimal('0.01')),
                                settings.CURRENCY_ABBREV,
                                fees,
                                settings.CURRENCY_ABBREV,
                            ),
                            error=False,
                            paymentmethod=method,
                        ).save()
                        break
                else:
                    # Unable to find the refund in the ledger. This could be a matter of timing,
                    # so yell about it but try agian.
                    raise CommandError("Trustly refund for invoice {0} was made in {1} instead of {2}, but could not be found in ledger.".format(r.invoice.pk, w['currency'], settings.CURRENCY_ABBREV))
            else:
                # Currency is correct, so check that the refunded amount is the same as
                # the one we expected.
                if Decimal(w['amount']) != r.fullamount:
                    raise CommandError("Mismatch in amount on Trustly refund for invoice {0} ({1} vs {2})".format(r.invoice.pk, Decimal(w['amount']), r.fullamount))
                fees = 0

            # Ok, things look good!
            TrustlyLog(message="Refund for order {0}, invoice {1}, completed".format(trustlytrans.orderid, r.invoice.pk), error=False, paymentmethod=method).save()
            manager.complete_refund(
                r.id,
                r.fullamount,
                fees,
                pm.config('accounting_income'),
                pm.config('accounting_fee'),
                [],
                method)
