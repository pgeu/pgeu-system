# Process reports from Adyen. This includes downloading them for storage,
# as well as processing the contents.
#
# Copyright (C) 2013, PostgreSQL Europe
#
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings

import re
import csv
import urllib2
import StringIO
from base64 import standard_b64encode
from datetime import datetime, date
from decimal import Decimal

from postgresqleu.adyen.models import AdyenLog, Report, TransactionStatus
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.accounting.util import create_accounting_entry


class Command(BaseCommand):
    help = 'Download and/or process reports from Adyen'

    def add_arguments(self, parser):
        parser.add_argument('--only', choices=('download', 'process'))
        parser.add_argument('-q', '--quiet', action='store_true')

    def handle(self, *args, **options):
        self.verbose = not options['quiet']

        if options['only'] in (None, 'download'):
            self.download_reports()

        if options['only'] in (None, 'process'):
            self.process_reports()

    def download_reports(self):
        # Download all currently pending reports (that we can)
        for report in Report.objects.filter(downloadedat=None).order_by('receivedat'):
            try:
                with transaction.atomic():
                    if self.verbose:
                        self.stdout.write("Downloading {0}".format(report.url))
                    req = urllib2.Request(report.url)
                    req.add_header('Authorization', 'Basic %s' % (
                        standard_b64encode('%s:%s' % (settings.ADYEN_REPORT_USER, settings.ADYEN_REPORT_PASSWORD)),
                        ))
                    u = urllib2.urlopen(req)
                    resp = u.read()
                    u.close()
                    if len(resp) == 0:
                        self.stderr.write("Downloaded report {0} and got zero bytes (no header). Not storing, will try again.".format(report.url))
                    else:
                        report.downloadedat = datetime.now()
                        report.contents = resp
                        report.save()
                        AdyenLog(message='Downloaded report {0}'.format(report.url), error=False).save()
            except Exception, ex:
                self.stderr.write("Failed to download report {0}: {1}".format(report.url, ex))
                # This might fail again if we had a db problem, but it should be OK as long as it
                # was just a download issue which is most likely.
                AdyenLog(message='Failed to download report %s: %s' % (report.url, ex), error=True).save()

    def process_payment_accounting_report(self, report):
        sio = StringIO.StringIO(report.contents)
        reader = csv.DictReader(sio, delimiter=',')
        for l in reader:
            # SentForSettle is what we call capture, so we track that
            # Settled is when we actually receive the money
            # Changes in Sep 2015 means Settled is sometimes SettledBulk
            # Everything else we ignore
            if l['Record Type'] == 'SentForSettle' or l['Record Type'] == 'Settled' or l['Record Type'] == 'SettledBulk':
                # Find the actual payment
                pspref = l['Psp Reference']
                bookdate = l['Booking Date']
                try:
                    trans = TransactionStatus.objects.get(pspReference=pspref)
                except TransactionStatus.DoesNotExist:
                    # Yes, for now we rollback the whole processing of this one
                    raise Exception('Transaction %s not found!' % pspref)
                if l['Record Type'] == 'SentForSettle':
                    # If this is a POS transaction, it typically received a
                    # separate CAPTURE notification, in which case the capture
                    # date is already set. But if not, we'll set it to the
                    # sent for settle date.
                    if not trans.capturedat:
                        trans.capturedat = bookdate
                        trans.method = l['Payment Method']
                        trans.save()
                        AdyenLog(message='Transaction %s captured at %s' % (pspref, bookdate), error=False).save()
                        if self.verbose:
                            self.stdout.write("Sent for settle on {0}".format(pspref))
                elif l['Record Type'] in ('Settled', 'SettledBulk'):
                    if trans.settledat is not None:
                        # Transaction already settled. But we might be reprocessing
                        # the report, so verify if the previously settled one is
                        # *identical*.
                        if trans.settledamount == Decimal(l['Main Amount'], 2):
                            self.stderr.write("Transaction {0} already settled at {2}, ignoring (NOT creating accounting record)!".format(pspref, trans.settledat))
                            continue
                        else:
                            raise CommandError('Transaction {0} settled more than once?!'.format(pspref))
                    if not trans.capturedat:
                        trans.capturedat = bookdate

                    trans.settledat = bookdate
                    trans.settledamount = Decimal(l['Main Amount'], 2)
                    trans.save()
                    if self.verbose:
                        self.stdout.write("Settled {0}, total amount {1}".format(pspref, trans.settledamount))
                    AdyenLog(message='Transaction %s settled at %s' % (pspref, bookdate), error=False).save()

                    # Settled transactions create a booking entry
                    accstr = "Adyen settlement %s" % pspref
                    accrows = [
                        (settings.ACCOUNTING_ADYEN_AUTHORIZED_ACCOUNT, accstr, -trans.amount, None),
                        (settings.ACCOUNTING_ADYEN_PAYABLE_ACCOUNT, accstr, trans.settledamount, None),
                        (settings.ACCOUNTING_ADYEN_FEE_ACCOUNT, accstr, trans.amount - trans.settledamount, trans.accounting_object),
                        ]
                    create_accounting_entry(date.today(), accrows, False)

    def process_received_payments_report(self, report):
        # We don't currently do anything with this report, but we store the contents
        # of them in case we might need them in the future.
        pass

    def process_settlement_detail_report_batch(self, report):
        # Summarize the settlement detail report in an email to to treasurer@, so they
        # can keep track of what's going on.

        # Get the batch number from the url
        batchnum = re.search('settlement_detail_report_batch_(\d+).csv$', report.url).groups(1)[0]

        # Now summarize the contents
        sio = StringIO.StringIO(report.contents)
        reader = csv.DictReader(sio, delimiter=',')
        types = {}
        for l in reader:
            t = l['Type']
            if t == 'Balancetransfer':
                # Balance transfer is special -- we can have two of them that evens out,
                # but we need to separate in and out
                if Decimal(l['Net Debit (NC)'] or 0) > 0:
                    t = "Balancetransfer2"

            lamount = Decimal(l['Net Credit (NC)'] or 0) - Decimal(l['Net Debit (NC)'] or 0)
            if t in types:
                types[t] += lamount
            else:
                types[t] = lamount

        def sort_types(a):
            # Special sort method that just ensures that Settled always ends up at the top
            # and the rest is just alphabetically sorted. (And yes, this is ugly code :P)
            if a[0] == 'Settled' or a[0] == 'SettledBulk':
                return 'AAA'
            return a[0]

        msg = "\n".join(["%-20s: %s" % (k, v) for k, v in sorted(types.iteritems(), key=sort_types)])
        acct = report.notification.merchantAccountCode

        # Generate an accounting record, iff we know what every row on the
        # statement actually is.
        acctrows = []
        accstr = "Adyen settlement batch %s for %s" % (batchnum, acct)
        for t, amount in types.items():
            if t == 'Settled' or t == 'SettledBulk':
                # Settled means we took it out of the payable balance
                acctrows.append((settings.ACCOUNTING_ADYEN_PAYABLE_ACCOUNT, accstr, -amount, None))
            elif t == 'MerchantPayout':
                # Amount directly into our checking account
                acctrows.append((settings.ACCOUNTING_ADYEN_PAYOUT_ACCOUNT, accstr, -amount, None))
            elif t == 'DepositCorrection' or t == 'Balancetransfer' or t == 'Balancetransfer2':
                # Modification of our deposit account - in either direction!
                acctrows.append((settings.ACCOUNTING_ADYEN_MERCHANT_ACCOUNT, accstr, -amount, None))
            elif t == 'InvoiceDeduction':
                # Adjustment of the invoiced costs. So adjust the payment fees!
                acctrows.append((settings.ACCOUNTING_ADYEN_FEE_ACCOUNT, accstr, -amount, None))
            elif t == 'Refunded' or t == 'RefundedBulk':
                # Refunded - should already be booked against the refunding account
                acctrows.append((settings.ACCOUNTING_ADYEN_REFUNDS_ACCOUNT, accstr, -amount, None))
            else:
                # Other rows that we don't know about will generate an open accounting entry
                # for manual fixing.
                pass
        if len(acctrows) == len(types):
            # If all entries were processed, the accounting entry should
            # automatically be balanced by now, so we can safely just complete it.
            create_accounting_entry(date.today(), acctrows, False)

            msg = "A settlement batch with Adyen has completed for merchant account %s. A summary of the entries are:\n\n%s\n\n" % (acct, msg)
        else:
            # All entries were not processed, so we write what we know to the
            # db, and then just leave the entry open.
            create_accounting_entry(date.today(), acctrows, True)

            msg = "A settlement batch with Adyen has completed for merchant account %s. At least one entry in this was UNKNOWN, and therefor the accounting record has been left open, and needs to be adjusted manually!\nA summary of the entries are:\n\n%s\n\n" % (acct, msg)

        send_simple_mail(settings.INVOICE_SENDER_EMAIL,
                         settings.ADYEN_NOTIFICATION_RECEIVER,
                         'Adyen settlement batch %s completed' % batchnum,
                         msg
                         )

    def process_reports(self):
        # Process all downloaded but unprocessed reports

        for report in Report.objects.filter(downloadedat__isnull=False, processedat=None).order_by('downloadedat'):
            try:
                with transaction.atomic():
                    if self.verbose:
                        self.stdout.write("Processing {0}".format(report.url))

                    # To know what to do, we look at the filename of the report URL
                    filename = report.url.split('/')[-1]
                    if filename.startswith('payments_accounting_report_'):
                        self.process_payment_accounting_report(report)
                    elif filename.startswith('received_payments_report'):
                        self.process_received_payments_report(report)
                    elif filename.startswith('settlement_detail_report_batch_'):
                        self.process_settlement_detail_report_batch(report)
                    else:
                        raise CommandError('Unknown report type in file "{0}"'.format(filename))

                    # If successful, flag as processed and add the log
                    report.processedat = datetime.now()
                    report.save()
                    AdyenLog(message='Processed report %s' % report.url, error=False).save()
            except Exception, ex:
                self.stderr.write("Failed to process report {0}: {1}".format(report.url, ex))
                AdyenLog(message='Failed to process report %s: %s' % (report.url, ex), error=True).save()
