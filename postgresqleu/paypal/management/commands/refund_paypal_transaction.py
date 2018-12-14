# -*- coding: utf-8 -*-
#
# Refund an individual paypal transactions (*not* an invoice, this was mainly
# created to deal with donation-spam from hacked accounts)
#
# Copyright (C) 2018, PostgreSQL Europe
#
from django.core.management.base import BaseCommand, CommandError

import time

from postgresqleu.paypal.models import TransactionInfo
from postgresqleu.paypal.util import PaypalAPI


class Command(BaseCommand):
    help = 'Refund paypal transactions'

    def add_arguments(self, parser):
        parser.add_argument('-i', '--ids', help='Transaction id from database', nargs='+', required=True)
        parser.add_argument('-m', '--message', help='Message', required=True)

    def handle(self, *args, **options):
        ids = [int(i) for i in options['ids']]
        translist = list(TransactionInfo.objects.filter(id__in=ids))
        if len(ids) != len(translist):
            foundids = set([t.id for t in translist])
            raise CommandError("Could not find ids %s" % ",".join([str(i) for i in set(ids).difference(foundids)]))

        for t in translist:
            if t.amount == 0:
                raise CommandError("Transaction {0}, zero euros.".format(t.id))
            if t.amount < 0:
                raise CommandError("Transaction {0}, already a refund.".format(t.id))

        print("Going to refund the following:")
        print("-----")
        fmtstr = "{0:8} {1:8} {2:40} {3:30}"
        print(fmtstr.format("id", "amount", "sender", "text"))
        for t in translist:
            print(fmtstr.format(t.id, t.amount, t.sender, t.transtext))
        print("-----")
        print("Each will be given the message:")
        print(options['message'])
        print("-----")

        while True:
            r = raw_input('OK to do this? ')
            if r.lower().startswith('y'):
                break
            if r.lower().startswith('n'):
                raise CommandError("OK, aborting")

        api = PaypalAPI()
        for t in translist:
            try:
                r = api.refund_transaction(t.paypaltransid, t.amount, True, options['message'])
                print("Successfully refunded {0} (paypal id {1}, refund id {2})".format(t.id, t.paypaltransid, r))
                time.sleep(1)
            except Exception, e:
                print("FAILED to refund {0} (paypal id {1}): {2}".format(t.id, t.paypaltransid, e))

        print("Done.")
