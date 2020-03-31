#
# These are the internal API entrypoints for the accounting system.
#

from django.db import connection, transaction
from django.db.models import Max
from django.conf import settings

from decimal import Decimal

from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.util.time import today_global

from .models import JournalEntry, JournalItem, JournalUrl
from .models import Object, Account, Year


class AccountingException(Exception):
    pass


def create_accounting_entry(items,
                            leaveopen=False,
                            urllist=None):
    # items must be an array of tuples in the format:
    # (accountnumber, descriptiontext, amount, objectname)
    # Positive amounts indicate debit, negative amounts indicate credit.
    # objects are referenced by *name* and looked up internally here.
    # Entries must be balanced unless leaveopen is set to True
    # Any urls listed in urllist must exist and be correct, no verification
    # is done.

    if not settings.ENABLE_AUTO_ACCOUNTING:
        return

    date = today_global()

    sid = transaction.savepoint()
    try:
        # Start by some simple validation
        for r in items:
            if r[2] == 0:
                raise AccountingException("Submitted accounting journal entry has a zero sum entry!")
            if Decimal(r[2]).as_tuple().exponent < -2:
                raise AccountingException("Submitted accounting journal entry has items that are not rounded off to two decimal points ({0})!".format(r[2]))

        debitsum = sum([r[2] for r in items if r[2] > 0])
        creditsum = -sum([r[2] for r in items if r[2] < 0])
        if debitsum != creditsum and not leaveopen:
            raise AccountingException("Submitted accounting journal entry is not balanced!")

        try:
            year = Year.objects.get(year=date.year)
        except Year.DoesNotExist:
            # If the year simply doesn't exist, we create one and send an alert about it.
            # This will handle the case of automated entries showing up very early in the year when
            # nobody has had time to deal with it manually yet.
            year = Year(year=date.year, isopen=True)
            year.save()

            send_simple_mail(
                settings.INVOICE_SENDER_EMAIL,
                settings.INVOICE_NOTIFICATION_RECEIVER,
                "Accounting year {} created".format(year.year),
                """An accounting entry for non-existing year {0} arrived,
so the year was automatically created and the entry added.

If this is in error, you will have to go remove the entry
and the year manually!
""".format(year.year),
            )
        if not year.isopen:
            # If the year exists but is closed, then it's actually an error.
            raise AccountingException("Year %s is not open for new entries!" % date.year)
        seq = JournalEntry.objects.filter(year=year).aggregate(Max('seq'))['seq__max']
        if seq is None:
            seq = 0

        # We assume the rest is correct and start building the db entries,
        # since we'll just roll it back if referenced data is missing.

        entry = JournalEntry(year=year, seq=seq + 1, date=date, closed=False)
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
                            description=description[:200]).save()
            except Account.DoesNotExist:
                raise AccountingException("Account %s does not exist!" % accountnum)
            except Object.DoesNotExist:
                raise AccountingException("Object %s does not exist!" % objectname)

        # If there are any URLs to attach, do so now
        if urllist:
            for url in urllist:
                JournalUrl(journal=entry, url=url).save()

        # All items saved correct. Close the entry if we have to. We verified
        # above that it's valid...
        if not leaveopen:
            entry.closed = True
            entry.save()

        # Ok, it seems it worked...
        transaction.savepoint_commit(sid)

        return entry
    except Exception as e:
        transaction.savepoint_rollback(sid)
        raise


def get_latest_account_balance(accountid):
    # Start from the year with the first incoming balance (meaning that the previous year
    # was closed and it was transferred) and sum up all accounting entries for the specified
    # account since then. We intentionally include open items, so we can track pending transfers
    # between the banks.
    cursor = connection.cursor()

    cursor.execute("""WITH incoming_balance(incoming_year, incoming_amount) AS (
  SELECT year_id, amount FROM accounting_incomingbalance WHERE account_id=%(account)s
  UNION ALL VALUES (0,0)
  ORDER BY year_id DESC LIMIT 1
)
SELECT sum(amount)+COALESCE((SELECT incoming_amount FROM incoming_balance),0)
 FROM accounting_journalitem ji INNER JOIN accounting_journalentry je ON ji.journal_id=je.id
  WHERE account_id=%(account)s
   AND  je.year_id >= (SELECT incoming_year FROM incoming_balance)""",
                   {
                       'account': accountid,
                   })

    return cursor.fetchall()[0][0]


def get_account_choices():
    return [(a.num, str(a)) for a in Account.objects.all()]
