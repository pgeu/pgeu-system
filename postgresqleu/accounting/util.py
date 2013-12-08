#
# This is the API entrypoints for the accounting system.
#

from django.db import transaction
from django.db.models import Max

from decimal import Decimal

from models import JournalEntry, JournalItem, Object, Account, Year

class AccountingException(Exception):
	pass


def create_accounting_entry(date,
							items,
							leaveopen=False):
	# items must be an array of tuples in the format:
	# (accountnumber, descriptiontext, amount, objectname)
	# Positive amounts indicate debit, negative amounts indicate credit.
	# objects are referenced by *named* and looked up internally here.
	# Entries must be balanced unless leaveopen is set to True
	sid = transaction.savepoint()
	try:
		# Start by some simple validation
		for r in items:
			if r[2] == 0:
				raise AccountingException("Submitted accounting journal entry has a zero sum entry!")
			if Decimal(r[2]).as_tuple().exponent < -2:
				raise AccountingException("Submitted accounting journal entry has items that are not rounded off to two decimal points!")

		debitsum = sum([r[2] for r in items if r[2] > 0])
		creditsum = -sum([r[2] for r in items if r[2] < 0])
		if debitsum != creditsum and not leaveopen:
			raise AccountingException("Submitted accounting journal entry is not balanced!")

		try:
			year = Year.objects.get(year=date.year)
		except Year.DoesNotExist:
			raise AccountingException("Year %s does not exist in the accounting system!" % date.year)
		if not year.isopen:
			raise AccountingException("Year %s is not open for new entries!" % date.year)
		seq = JournalEntry.objects.filter(year=year).aggregate(Max('seq'))['seq__max']
		if seq is None: seq = 0

		# We assume the rest is correct and start building the db entries,
		# since we'll just roll it back if referenced data is missing.

		entry = JournalEntry(year=year, seq=seq+1, date=date, closed=False)
		entry.save()

		for accountnum, description, amount, objectname in items:
			try:
				account = Account.objects.get(num=accountnum)
				if objectname:
					obj = Object.objects.get(name=objectname)
				else:
					obj = None
				JournalItem(journal=entry,
							account=account,
							amount=amount,
							object=obj,
							description=description).save()
			except Account.DoesNotExist:
				raise AccountingException("Account %s does not exist!" % accountnum)
			except Object.DoesNotExist:
				raise AccountingException("Object %s does not exist!" % objectname)
		# All items saved correct. Close the entry if we have to. We verified
		# above that it's valid...
		if not leaveopen:
			entry.closed = True
			entry.save()

		# Ok, it seems it worked...
		transaction.savepoint_commit(sid)
	except:
		transaction.savepoint_rollback(sid)
		raise
