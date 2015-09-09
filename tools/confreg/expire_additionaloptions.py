#!/usr/bin/env python
#
# Expire additional options on pending registration that have not
# been paid on time, so others can get those seats.
#
# Copyright (C) 2015, PostgreSQL Europe
#

import os
import sys
from collections import defaultdict
from StringIO import StringIO

# Set up to run in django environment
from django.core.management import setup_environ
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), '../../postgresqleu'))
import settings
setup_environ(settings)

from django.db import transaction, connection

from postgresqleu.mailqueue.util import send_simple_mail

from postgresqleu.confreg.util import expire_additional_options

from postgresqleu.confreg.models import ConferenceRegistration

if __name__ == "__main__":
	with transaction.commit_on_success():
		# Expiry of additional options is based on when the registration was last modified, and not
		# the actual additional option. But the 99.9% case is people who are not touching their
		# registration at all, so this is not a problem. If they go in and change their address,
		# they get an additional grace period only.
		#
		# We also don't expire any registrations that have an invoice or a bulk registration. Those
		# are handled by the invoice cancellation.
		#
		# Pending additional options make no difference here because they are not actually added
		# to the registration, and the pending order itself will be canceled along with the invoice.
		#
		# And no - the django ORM does not like to do date math in the WHERE clause, AFAICT, when the
		# values come from different tables.
		regs = ConferenceRegistration.objects.filter(payconfirmedat__isnull=True,
													 invoice__isnull=True,
													 bulkpayment__isnull=True,
													 additionaloptions__invoice_autocancel_hours__isnull=False,
												 ).extra(
													 where=["lastmodified < CURRENT_TIMESTAMP - confreg_conferenceadditionaloption.invoice_autocancel_hours * '1 hour'::interval",]
												 )

		expired = defaultdict(list)
		for r in regs:
			expired[r.conference].extend([(r.firstname + ' ' + r.lastname, x) for x in expire_additional_options(r)])

		if expired:
			for conference, expired in expired.items():
				s = StringIO()
				s.write("""The following additional options have been removed from pending
registrations (without invoice or bulk payment) based on the invoice
autocancel hours, to make room for other attendees:

""")
				for name, option in expired:
					s.write(u"{0:<40}{1}\n".format(name, option))
				s.write("\n\n")
				send_simple_mail(conference.contactaddr,
								 conference.contactaddr,
								 'Additional options removed from pending registrations',
								 s.getvalue(),
								 sendername=conference.conferencename)

	connection.close()
