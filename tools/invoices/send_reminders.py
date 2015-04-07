#!/usr/bin/env python
#
# Send invoice reminders.
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
from postgresqleu.invoices.util import InvoiceWrapper


if __name__ == "__main__":
	with transaction.commit_on_success():
		# We send reminder automatically when an invoice is 1 day overdue.
		# We never send a second reminder, that is done manually.
		invoices = Invoice.objects.filter(finalized=True, deleted=False, refunded=False, paidat__isnull=True, remindersent__isnull=True, duedate__lt=datetime.now() - timedelta(days=1))
		for invoice in invoices:
			wrapper = InvoiceWrapper(invoice)
			wrapper.email_reminder()
			invoice.remindersent=datetime.now()
			invoice.save()
			print "Sent invoice reminder for #%s - %s" % (invoice.id, invoice.title)

	connection.close()
