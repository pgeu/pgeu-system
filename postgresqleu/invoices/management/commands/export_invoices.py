#!/usr/bin/env python
#
# Export invoices to PDF files
#
# Copyright (C) 2025, PostgreSQL Europe
#
from django.core.management.base import BaseCommand

import base64
import os
import sys

from postgresqleu.invoices.models import Invoice


class Command(BaseCommand):
    help = 'Export invoices by id'

    def add_arguments(self, parser):
        parser.add_argument('--invoice', action='store_true')
        parser.add_argument('--receipt', action='store_true')
        parser.add_argument('directory')
        parser.add_argument('idlist', nargs='+', type=int)

    def handle(self, *args, **options):
        if not os.path.isdir(options['directory']):
            print('{} is not a directory.'.format(options['directory']))
            sys.exit(1)

        if not (options['invoice'] or options['receipt']):
            print("Must specify at least one of --invoice and --receipt")
            sys.exit(1)

        invoices = Invoice.objects.filter(id__in=options['idlist'])
        if len(invoices) != len(options['idlist']):
            # Missing some invoices!
            print("Can't find invoices with ids {}".format(", ".join(
                (str(i) for i in set(options['idlist']).difference(set([i.id for i in invoices])))
            )))
            sys.exit(1)

        for i in invoices:
            if options['invoice']:
                with open(os.path.join(options['directory'], 'invoice_{}.pdf'.format(i.id)), 'wb') as f:
                    f.write(base64.b64decode(i.pdf_invoice))
            if options['receipt']:
                with open(os.path.join(options['directory'], 'receipt_{}.pdf'.format(i.id)), 'wb') as f:
                    f.write(base64.b64decode(i.pdf_receipt))

        print("Exported {} invoices.".format(len(invoices)))
