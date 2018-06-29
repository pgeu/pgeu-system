#
# This script compares the balance on the paypal account with the one
# in the accounting system, raising an alert if they are different
# (which indicates that something has been incorrectly processed).
#
# Copyright (C) 2010-2016, PostgreSQL Europe
#


from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from postgresqleu.paypal.util import PaypalAPI
from postgresqleu.accounting.util import get_latest_account_balance
from postgresqleu.mailqueue.util import send_simple_mail

class Command(BaseCommand):
	help = 'Compare paypal balance to the accounting system'

	@transaction.atomic
	def handle(self, *args, **options):
		api = PaypalAPI()

		# We only ever care about the primary currency
		paypal_balance = api.get_primary_balance()

		accounting_balance = get_latest_account_balance(settings.ACCOUNTING_PAYPAL_INCOME_ACCOUNT)

		if accounting_balance != paypal_balance:
			send_simple_mail(settings.INVOICE_SENDER_EMAIL,
							 settings.PAYPAL_REPORT_RECEIVER,
							 'Paypal balance mismatch!',
							 """Paypal balance ({0}) does not match the accounting system ({1})!

This could be because some entry has been missed in the accouting
(automatic or manual), or because of an ongoing booking of something
that the system deosn't know about.

Better go check manually!
""".format(paypal_balance, accounting_balance))
