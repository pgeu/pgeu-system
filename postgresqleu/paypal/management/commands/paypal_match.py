# -*- coding: utf-8 -*-
#
# This is a very trivial match runner for paypal, which just calls into
# the main invoice system to match payments.
#
# A previous version of the script used to do a lot more elaborate matching,
# but all that logic is now folded into the main invoicing system.
#
# We still maintain paypal-specific state in the database though.
#
# Copyright (C) 2010-2019, PostgreSQL Europe
#
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from datetime import datetime

from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.accounting.util import create_accounting_entry
from postgresqleu.paypal.models import TransactionInfo, ErrorLog


class Command(BaseCommand):
    help = 'Match pending paypal payments'

    class ScheduledJob:
        # This job gets scheduled to run after paypal_fetch only.
        internal = True

        @classmethod
        def should_run(self):
            if not InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.paypal.Paypal').exists():
                return False
            if not TransactionInfo.objects.filter(matched=False).exists():
                return False
            return True

    @transaction.atomic
    def handle(self, *args, **options):
        invoicemanager = InvoiceManager()

        # There may be multiple accounts, so loop over them
        for method in InvoicePaymentMethod.objects.filter(active=True, classname='postgresqleu.util.payment.paypal.Paypal'):
            pm = method.get_implementation()

            translist = TransactionInfo.objects.filter(matched=False, paymentmethod=method).order_by('timestamp')

            for trans in translist:
                # URLs for linkback to paypal
                urls = ["%s?cmd=_view-a-trans&id=%s" % (pm.get_baseurl(), trans.paypaltransid, ), ]

                # Manual handling of some record types

                # Record type: donation
                if trans.transtext == pm.config('donation_text'):
                    trans.setmatched('Donation, automatically matched by script')

                    # Generate a simple accounting record, that will have to be
                    # manually completed.
                    accstr = "Paypal donation %s" % trans.paypaltransid
                    accrows = [
                        (pm.config('accounting_income'), accstr, trans.amount - trans.fee, None),
                        (pm.config('accounting_fee'), accstr, trans.fee, None),
                        (settings.ACCOUNTING_DONATIONS_ACCOUNT, accstr, -trans.amount, None),
                        ]
                    create_accounting_entry(trans.timestamp.date(), accrows, True, urls)
                    continue
                # Record type: payment, but with no notice (auto-generated elsewhere, the text is
                # hard-coded in paypal_fetch.py
                if trans.transtext == "Paypal payment with empty note":
                    trans.setmatched('Empty payment description, leaving for operator')

                    accstr = "Unlabeled paypal payment from {0}".format(trans.sender)
                    accrows = [
                        (pm.config('accounting_income'), accstr, trans.amount - trans.fee, None),
                    ]
                    if trans.fee:
                        accrows.append(
                            (pm.config('accounting_fee'), accstr, trans.fee, None),
                        )
                    create_accounting_entry(trans.timestamp.date(), accrows, True, urls)
                    continue
                # Record type: transfer
                if trans.amount < 0 and trans.transtext == 'Transfer from Paypal to bank':
                    trans.setmatched('Bank transfer, automatically matched by script')
                    # There are no fees on the transfer, and the amount is already
                    # "reversed" and will automatically become a credit entry.
                    accstr = 'Transfer from Paypal to bank'
                    accrows = [
                        (pm.config('accounting_income'), accstr, trans.amount, None),
                        (pm.config('accounting_transfer'), accstr, -trans.amount, None),
                        ]
                    create_accounting_entry(trans.timestamp.date(), accrows, True, urls)
                    continue
                textstart = 'Refund of Paypal payment: {0} refund '.format(settings.ORG_SHORTNAME)
                if trans.amount < 0 and trans.transtext.startswith(textstart):
                    trans.setmatched('Matched API initiated refund')
                    # API initiated refund, so we should be able to match it
                    invoicemanager.complete_refund(
                        trans.transtext[len(textstart):],
                        -trans.amount,
                        -trans.fee,
                        pm.config('accounting_income'),
                        pm.config('accounting_fee'),
                        urls,
                        method,
                    )

                    # Accounting record is created by invoice manager
                    continue
                # Record type: outgoing payment (or manual refund)
                if trans.amount < 0:
                    trans.setmatched('Outgoing payment or manual refund, automatically matched by script')
                    # Refunds typically have a fee (a reversed fee), whereas pure
                    # payments don't have one. We don't make a difference of them
                    # though - we leave the record open for manual verification
                    accrows = [
                        (pm.config('accounting_income'), trans.transtext[:200], trans.amount - trans.fee, None),
                    ]
                    if trans.fee != 0:
                        accrows.append((pm.config('accounting_fee'), trans.transtext[:200], trans.fee, None),)
                    create_accounting_entry(trans.timestamp.date(), accrows, True, urls)
                    continue

                # Otherwise, it's an incoming payment. In this case, we try to
                # match it to an invoice.

                # Log things to the db
                def payment_logger(msg):
                    # Write the log output to somewhere interesting!
                    ErrorLog(timestamp=datetime.now(),
                             sent=False,
                             message='Paypal %s by %s (%s) on %s: %s' % (
                                 trans.paypaltransid,
                                 trans.sender,
                                 trans.sendername,
                                 trans.timestamp,
                                 msg
                                 ),
                             paymentmethod=method,
                    ).save()

                (r, i, p) = invoicemanager.process_incoming_payment(trans.transtext,
                                                                    trans.amount,
                                                                    "Paypal id %s, from %s <%s>" % (trans.paypaltransid, trans.sendername, trans.sender),
                                                                    trans.fee,
                                                                    pm.config('accounting_income'),
                                                                    pm.config('accounting_fee'),
                                                                    urls,
                                                                    payment_logger,
                                                                    method,
                )

                if r == invoicemanager.RESULT_OK:
                    trans.setmatched('Matched standard invoice')
                else:
                    # Logging is done by the invoice manager callback
                    pass
