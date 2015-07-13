#!/usr/bin/env python
#
# Cancel invoices that have passed their auto-cancel time
#
# Copyright (C) 2015, PostgreSQL Europe
#

import os
import sys
from datetime import datetime, timedelta

# Set up to run in django environment
from django.core.management import setup_environ
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../postgresqleu'))
import settings
setup_environ(settings)

from django.db import transaction, connection


from postgresqleu.invoices.models import Invoice
from postgresqleu.invoices.util import InvoiceManager


if __name__ == "__main__":
	with transaction.commit_on_success():
		invoices = Invoice.objects.filter(finalized=True, deleted=False, refunded=False, paidat__isnull=True, canceltime__lt=datetime.now())

		manager = InvoiceManager()

		for invoice in invoices:
			print "Canceling invoice %s, expired" % invoice.id

			# The manager will automatically cancel any registrations etc,
			# as well as send an email to the user.
			manager.cancel_invoice(invoice,
								   "Invoice passed automatic cancel time {0}".format(invoice.canceltime))

	connection.close()
