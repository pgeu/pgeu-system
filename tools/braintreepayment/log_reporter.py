#!/usr/bin/env python
#
# This script sends out reports of errors in the Braintree integration as
# a summary email.
#

# Copyright (C) 2015, PostgreSQL Europe
#

import os
import sys

# Set up to run in django environment
from django.core.management import setup_environ
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../postgresqleu'))
import settings
setup_environ(settings)

from StringIO import StringIO

from django.db import transaction, connection

from postgresqleu.braintreepayment.models import BraintreeLog
from postgresqleu.mailqueue.util import send_simple_mail



if __name__=="__main__":
	with transaction.commit_on_success():
		lines = list(BraintreeLog.objects.filter(error=True,sent=False).order_by('timestamp'))
		if len(lines):
			sio = StringIO()
			sio.write("The following error events have been logged by the Braintree integration:\n\n")
			for l in lines:
				sio.write("%s: %20s: %s\n" % (l.timestamp, l.transid, l.message))
				l.sent = True
				l.save()
			sio.write("\n\n\nAll these events have now been tagged as sent, and will no longer be\nprocessed by the system in any way.\n")

			send_simple_mail(settings.INVOICE_SENDER_EMAIL,
							 settings.BRAINTREE_NOTIFICATION_RECEIVER,
							 'Braintree integration error report',
							 sio.getvalue())

	connection.close()
