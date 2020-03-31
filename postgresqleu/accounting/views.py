from django.http import HttpResponseRedirect, Http404, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, get_object_or_404
from django.forms.models import inlineformset_factory
from django.db.models import Max
from django.db import connection, transaction
from django.core.paginator import Paginator

from datetime import datetime

from postgresqleu.util.request import get_int_or_error
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.util.time import today_global

from .models import JournalEntry, JournalItem, JournalUrl, Year, Object
from .models import IncomingBalance, Account
from .forms import JournalEntryForm, JournalItemForm, JournalItemFormset, JournalUrlForm
from .forms import CloseYearForm


def index(request):
    authenticate_backend_group(request, 'Accounting managers')
    # Always redirect to the current year
    return HttpResponseRedirect("%s/" % today_global().year)


def _setup_search(request, term):
    if term:
        request.session['searchterm'] = term
    else:
        if 'searchterm' in request.session:
            del request.session['searchterm']


def _perform_search(request, year):
    if 'searchterm' in request.session:
        searchterm = request.session['searchterm']
        return (searchterm,
                list(
                    JournalEntry.objects.filter(year=year, journalitem__description__icontains=searchterm)
                    .distinct().order_by('closed', '-date', '-id')))

    return ('', list(JournalEntry.objects.filter(year=year).order_by('closed', '-date', '-id')))


def _get_reportable_objects(year):
    return Object.objects.extra(where=('EXISTS (SELECT 1 FROM accounting_journalitem i INNER JOIN accounting_journalentry e ON e.id=i.journal_id WHERE i.object_id=accounting_object.id AND e.year_id=%s)', ), params=(year.year, ))


class EntryPaginator(Paginator):
    ENTRIES_PER_PAGE = 50

    def __init__(self, entries):
        return super(EntryPaginator, self).__init__(entries, self.ENTRIES_PER_PAGE)

    def get_pages(self, currentpage):
        if self.num_pages > 10:
            # More than 10 won't fit, so split

            if currentpage < 6:
                return list(self.page_range)[:10]
            elif currentpage > self.num_pages - 5:
                return list(self.page_range)[-10:]
            else:
                return list(self.page_range)[currentpage - 5:currentpage - 5 + 10]
        else:
            return self.page_range


@transaction.atomic
def year(request, year):
    authenticate_backend_group(request, 'Accounting managers')

    try:
        year = Year.objects.get(year=int(year))
    except Year.DoesNotExist:
        # Year does not exist, but what do we do about it?
        if int(year) == today_global().year:
            # For current year, we automatically create the year and move on
            year = Year(year=int(year), isopen=True)
            year.save()
            messages.info(request, "Year {} did not exist in the system, but since it's the current year it has now been created.".format(year.year))
        else:
            return HttpResponse("Year {} does not exist in the system, and is not current year.".format(int(year)))

    if 'search' in request.GET:
        _setup_search(request, request.GET['search'])
        return HttpResponseRedirect('/accounting/%s/' % year.year)

    (searchterm, entries) = _perform_search(request, year)

    paginator = EntryPaginator(entries)
    currpage = get_int_or_error(request.GET, 'p', 1)

    return render(request, 'accounting/main.html', {
        'entries': paginator.page(currpage),
        'page': currpage,
        'pages': paginator.get_pages(currpage),
        'numpages': paginator.num_pages,
        'hasopen': any([not e.closed for e in entries]),
        'year': year,
        'years': Year.objects.all(),
        'reportable_objects': _get_reportable_objects(year),
        'searchterm': searchterm,
        })


@transaction.atomic
def new(request, year):
    authenticate_backend_group(request, 'Accounting managers')

    year = int(year)

    # Default the date to the same date as the last entry for this year,
    # provided one exists. Otherwise, just the start of the year.
    try:
        lastentry = JournalEntry.objects.filter(year=year).order_by('-date')[0]
        d = lastentry.date
    except IndexError:
        d = date(year, 1, 1)

    year = get_object_or_404(Year, year=year)
    highseq = JournalEntry.objects.filter(year=year).aggregate(Max('seq'))['seq__max']
    if highseq is None:
        highseq = 0
    entry = JournalEntry(year=year, seq=highseq + 1, date=d, closed=False)
    entry.save()

    # Disable any search query to make sure we can actually see
    # the record we've just created.
    _setup_search(request, '')

    return HttpResponseRedirect('/accounting/e/%s/' % entry.pk)


@transaction.atomic
def entry(request, entryid):
    authenticate_backend_group(request, 'Accounting managers')

    entry = get_object_or_404(JournalEntry, pk=entryid)

    if 'search' in request.GET:
        _setup_search(request, request.GET['search'])
        return HttpResponseRedirect('/accounting/e/%s/' % entryid)

    (searchterm, entries) = _perform_search(request, entry.year)

    paginator = EntryPaginator(entries)
    currpage = get_int_or_error(request.GET, 'p', 1)

    extra = max(2, 6 - entry.journalitem_set.count())
    inlineformset = inlineformset_factory(JournalEntry, JournalItem, JournalItemForm, JournalItemFormset, can_delete=True, extra=extra)
    inlineurlformset = inlineformset_factory(JournalEntry, JournalUrl, JournalUrlForm, can_delete=True, extra=2, exclude=[])

    if request.method == 'POST':
        if request.POST['submit'] == 'Delete':
            year = entry.year
            entry.delete()
            return HttpResponseRedirect("/accounting/%s/" % year.year)

        form = JournalEntryForm(data=request.POST, instance=entry)
        formset = inlineformset(data=request.POST, instance=entry)
        urlformset = inlineurlformset(data=request.POST, instance=entry)

        if form.is_valid():
            if formset.is_valid() and urlformset.is_valid():
                instance = form.save()
                formset.save()
                urlformset.save()

                if request.POST['submit'] == 'Close':
                    instance.closed = True
                    instance.save()
                return HttpResponseRedirect(".")
        # Else fall through
    else:
        form = JournalEntryForm(instance=entry)
        formset = inlineformset(instance=entry)
        urlformset = inlineurlformset(instance=entry)

    items = list(entry.journalitem_set.all())
    totals = (sum([i.amount for i in items if i.amount > 0]),
              -sum([i.amount for i in items if i.amount < 0]))
    urls = list(entry.journalurl_set.all())
    return render(request, 'accounting/main.html', {
        'entries': paginator.page(currpage),
        'page': currpage,
        'pages': paginator.get_pages(currpage),
        'numpages': paginator.num_pages,
        'hasopen': any([not e.closed for e in entries]),
        'year': entry.year,
        'entry': entry,
        'has_pending_banktrans': entry.pendingbankmatcher_set.exists(),
        'items': items,
        'urls': urls,
        'totals': totals,
        'form': form,
        'formset': formset,
        'urlformset': urlformset,
        'years': Year.objects.all(),
        'reportable_objects': _get_reportable_objects(entry.year),
        'searchterm': searchterm,
        })


def _get_balance_query(objstr='', includeopen=False):
    q = """WITH currentyear AS (
 SELECT account_id AS accountnum, sum(amount) FILTER (WHERE je.closed) as closedamount, sum(amount) FILTER (WHERE NOT je.closed) as openamount FROM accounting_journalitem ji INNER JOIN accounting_journalentry je ON ji.journal_id=je.id WHERE je.year_id=%(year)s AND je.date <= %(enddate)s """ + objstr + """ GROUP BY account_id
),incoming AS (
 SELECT account_id AS accountnum, amount FROM accounting_incomingbalance WHERE year_id=%(year)s
), fullbalance AS (
SELECT coalesce(currentyear.accountnum, incoming.accountnum) as anum, coalesce(currentyear.closedamount,0) AS currentamount, coalesce(currentyear.openamount,0) as openamount, coalesce(incoming.amount,0) AS incomingamount FROM currentyear FULL OUTER JOIN incoming ON currentyear.accountnum=incoming.accountnum
)
SELECT ac.name AS acname, ag.name AS agname, anum, a.name,
 count(*) over (partition by ag.name) = 1 and foldable as agfold,
    """

    def _get_sumcol(sourcecol, partition):
        return "sum(%s*case when balancenegative then -1 else 1 end) over (partition by %s)" % (sourcecol, partition)

    def _get_negcol(sourcecol):
        return "%s*case when balancenegative then -1 else 1 end" % sourcecol

    def _get_totalcol(sourcecol):
        return "sum(%s) over ()" % sourcecol

    src = ['incomingamount', 'currentamount']
    if includeopen:
        src.extend(['openamount', '(currentamount+openamount)', '(incomingamount+currentamount+openamount)'])
    else:
        src.append('(incomingamount+currentamount)')

    q += ",\n".join([
        ",\n".join([_get_sumcol(x, "ac.name") for x in src]),
        ",\n".join([_get_sumcol(x, "ag.name") for x in src]),
        ",\n".join([_get_negcol(x) for x in src]),
        ",\n".join([_get_totalcol(x) for x in src])
        ])

    q += """
 FROM accounting_accountclass ac
    INNER JOIN accounting_accountgroup ag ON ac.id=ag.accountclass_id
    INNER JOIN accounting_account a ON ag.id=a.group_id
    INNER JOIN fullbalance ON fullbalance.anum=a.num
 WHERE ac.inbalance AND (incomingamount != 0 OR currentamount != 0)
 ORDER BY anum
        """
    return q


def _collate_results(query, queryparam, numvalues):
    results = []
    lastag = ''
    lastagfold = False
    lastagvals = None
    lastac = ''
    lastacvals = None
    currentag = []
    currentac = []
    totalresult = None

    curs = connection.cursor()
    curs.execute(query, queryparam)

    for row in curs.fetchall():
        row = list(row)
        acname = row.pop(0)
        agname = row.pop(0)
        anum = row.pop(0)
        aname = row.pop(0)
        agfold = row.pop(0)

        acvals = row[:numvalues]
        row[:numvalues] = []
        agvals = row[:numvalues]
        row[:numvalues] = []
        avals = row[:numvalues]
        row[:numvalues] = []
        if not totalresult:
            totalresult = row[:numvalues]
        row[:numvalues] = []

        if len(row) != 0:
            raise Exception("Invalid number of entries left in row: %s" % len(row))

        if agname != lastag:
            if currentag:
                currentac.append([lastag, currentag, lastagfold, lastagvals])
                currentag = []
            lastag = agname
            lastagfold = agfold
            lastagvals = agvals
        currentag.append([anum, aname, avals])

        if acname != lastac:
            if currentac:
                results.append([lastac, currentac, lastacvals])
                currentac = []
            lastac = acname
            lastacvals = acvals

    if currentag:
        currentac.append([lastag, currentag, lastagfold, lastagvals])
    if currentac:
        results.append([lastac, currentac, lastacvals])

    return (results, totalresult)


@transaction.atomic
def closeyear(request, year):
    authenticate_backend_group(request, 'Accounting managers')

    year = Year.objects.get(pk=year)
    hasopen = JournalEntry.objects.filter(year=year, closed=False).exists()
    try:
        nextyear = Year.objects.get(year=year.year + 1)
        hasnext = IncomingBalance.objects.filter(year=nextyear).exists()
    except Year.DoesNotExist:
        hasnext = False

    curs = connection.cursor()
    # This is mostly the same as the _getbalancequery(), but we don't include
    # the recalculations required specifically to the balancenegative
    # field.
    curs.execute("""WITH currentyear AS (
 SELECT account_id AS accountnum, sum(amount) as amount FROM accounting_journalitem ji INNER JOIN accounting_journalentry je ON ji.journal_id=je.id WHERE je.year_id=%(year)s AND je.date <= %(enddate)s AND je.closed GROUP BY account_id
), incoming AS (
 SELECT account_id AS accountnum, amount FROM accounting_incomingbalance WHERE year_id=%(year)s
), fullbalance AS (
SELECT coalesce(currentyear.accountnum, incoming.accountnum) as anum, coalesce(currentyear.amount,0) AS currentamount, coalesce(incoming.amount,0) AS incomingamount FROM currentyear FULL OUTER JOIN incoming ON currentyear.accountnum=incoming.accountnum
)
SELECT ac.name AS acname, ag.name AS agname, anum, a.name,
 count(*) over (partition by ag.name) = 1 and foldable as agfold,
 incomingamount,
 currentamount,
 (incomingamount+currentamount) as outgoingamount,
 sum(incomingamount) over() as incomingtotal,
 sum(currentamount) over () as currenttotal,
 sum((incomingamount+currentamount)) over () as outgoingtotal
 FROM accounting_accountclass ac INNER JOIN accounting_accountgroup ag ON ac.id=ag.accountclass_id INNER JOIN accounting_account a ON ag.id=a.group_id INNER JOIN fullbalance ON fullbalance.anum=a.num WHERE ac.inbalance AND (incomingamount != 0 OR currentamount != 0) ORDER BY anum
        """, {
        'year': year.year,
        'enddate': date(year.year, 12, 31),
        })
    balance = [dict(list(zip([col[0] for col in curs.description], row))) for row in curs.fetchall()]
    curs.execute("SELECT sum(-amount) FROM accounting_journalitem ji INNER JOIN accounting_journalentry je ON ji.journal_id=je.id INNER JOIN accounting_account a ON ji.account_id=a.num INNER JOIN accounting_accountgroup ag ON ag.id=a.group_id INNER JOIN accounting_accountclass ac ON ac.id=ag.accountclass_id WHERE je.year_id=%(year)s AND NOT inbalance", {
        'year': year.year,
    })
    yearresult = curs.fetchall()[0][0]

    if request.method == 'POST':
        form = CloseYearForm(balance, data=request.POST)
        if form.is_valid():
            # Ok, let's do this :)
            # Create a new year if we have to
            (nextyear, created) = Year.objects.get_or_create(year=year.year + 1, defaults={'isopen': True})

            # Start by transferring this years result
            IncomingBalance(year=nextyear,
                            account=form.cleaned_data['account'],
                            amount=-yearresult
                            ).save()

            # Now add all other outgoing balances
            for a in balance:
                if a['outgoingamount'] != 0:
                    IncomingBalance(year=nextyear,
                                    account=Account.objects.get(num=a['anum']),
                                    amount=a['outgoingamount']
                                    ).save()
            # Then close the year
            year.isopen = False
            year.save()

            return HttpResponseRedirect('/accounting/%s/' % year.year)
    else:
        form = CloseYearForm(balance)

    return render(request, 'accounting/closeyear.html', {
        'year': year,
        'hasopen': hasopen,
        'hasnext': hasnext,
        'outgoingbalance': balance,
        'yearresult': yearresult,
        'form': form,
        'years': Year.objects.all(),
        'reportable_objects': _get_reportable_objects(year),
    })


@transaction.atomic
def report(request, year, reporttype):
    authenticate_backend_group(request, 'Accounting managers')

    years = list(Year.objects.all())
    year = get_object_or_404(Year, year=year)

    mindate = maxdate = None
    suppress_years = False

    if request.GET.get('obj', None):
        object = get_object_or_404(Object, pk=get_int_or_error(request.GET, 'obj'))
        objstr = "AND ji.object_id=%s" % object.id
    else:
        object = None
        objstr = ''

    hasopenentries = JournalEntry.objects.filter(year=year, closed=False).exists()

    if request.GET.get('acc', None):
        account = get_object_or_404(Account, num=get_int_or_error(request.GET, 'acc'))
    else:
        account = None

    if request.GET.get('ed', None) and request.GET['ed'] != 'undefined':
        enddate = datetime.strptime(request.GET['ed'], '%Y-%m-%d').date()
        if year and enddate.year != year.year:
            enddate = date(year.year, 12, 31)
    else:
        enddate = date(year.year, 12, 31)

    if request.GET.get('io', 0) == '1':
        includeopen = True
    else:
        includeopen = False

    filtered_objects = _get_reportable_objects(year)

    if reporttype == 'ledger':
        # This is a special report, so we don't use the collate functionality
        # XXX: consider perhaps including the in and out balance as well.

        # Yup, the django ORM fails again - no window aggregates
        sql = "SELECT a.num as accountnum, a.name as accountname, sum(i.amount) FILTER (WHERE i.amount > 0) over w1 as totaldebit, sum(-i.amount) FILTER (WHERE i.amount < 0) over w1 as totalcredit, e.seq as entryseq, e.date, i.description, case when i.amount > 0 then i.amount else 0 end as debit, case when i.amount < 0 then -i.amount else 0 end as credit, o.name as object, e.closed FROM accounting_journalitem i INNER JOIN accounting_account a ON i.account_id=a.num INNER JOIN accounting_journalentry e ON i.journal_id=e.id LEFT JOIN accounting_object o ON i.object_id=o.id WHERE e.year_id=%(year)s AND (e.closed OR %(includeopen)s) AND e.date<=%(enddate)s"
        params = {
            'year': year.year,
            'enddate': enddate,
            'includeopen': includeopen,
            }
        if request.GET.get('obj', None):
            sql += " AND o.id=%(objectid)s"
            params['objectid'] = get_int_or_error(request.GET, 'obj')
        if request.GET.get('acc', None):
            sql += " AND a.num=%(account)s"
            params['account'] = get_int_or_error(request.GET, 'acc')
        sql += " WINDOW w1 AS (PARTITION BY a.num) ORDER BY a.num, e.date, e.seq"
        curs = connection.cursor()
        curs.execute(sql, params)

        # Django templates are also too stupid to be able to produce
        # a section-summary value, so we need to build them up as
        # a two stage array.
        items = []
        lastaccount = 0
        for row in curs.fetchall():
            if row[0] != lastaccount:
                items.append({'accountnum': row[0],
                              'accountname': row[1],
                              'totaldebit': row[2],
                              'totalcredit': row[3],
                              'entries': []
                              })
                lastaccount = row[0]
            items[-1]['entries'].append(dict(list(zip([col[0] for col in curs.description[4:]], row[4:]))))

        return render(request, 'accounting/ledgerreport.html', {
            'year': year,
            'years': years,
            'reportable_objects': filtered_objects,
            'currentobj': object,
            'accounts': Account.objects.all(),
            'currentaccount': account,
            'reporttype': 'ledger',
            'title': 'Ledger',
            'items': items,
            'enddate': enddate,
            'hasopenentries': hasopenentries,
            'includeopen': includeopen,
            'yearsuffix': 'report/ledger/',
            'isreport': True,
        })
    elif reporttype == 'results':
        # The results report is the easiest one, since we can assume that
        # all accounts enter the year with a value 0. Therefor, we only
        # care about summing the data for this year.
        # We only show accounts that have had some transactions on them.
        # Note! Probably sync up much of this query with the object report!
        (results, totalresult) = _collate_results(
            """WITH t AS (
SELECT ac.name as acname,
       ag.name as agname,
       ag.foldable,
       a.num as anum,
       a.name,
       sum(-ji.amount) as amount
FROM accounting_accountclass ac
INNER JOIN accounting_accountgroup ag ON ac.id=ag.accountclass_id
INNER JOIN accounting_account a ON ag.id=a.group_id
INNER JOIN accounting_journalitem ji ON ji.account_id=a.num
INNER JOIN accounting_journalentry je ON je.id=ji.journal_id
WHERE je.year_id=%(year)s
  AND je.date <= %(enddate)s
  AND (je.closed or %(includeopen)s)
  AND NOT ac.inbalance
{0}
GROUP BY ac.name, ag.name, ag.foldable, a.id, a.name
)
SELECT acname,
       agname,
       anum,
       name,
       count(*) OVER (PARTITION BY agname) = 1 AND foldable as agfold,
       sum(amount) OVER (PARTITION by acname) AS acamount,
       sum(amount) OVER (PARTITION by agname) AS agamount,
       amount,
       sum(amount) OVER ()
FROM t
ORDER BY anum""".format(objstr),
            {
                'year': year.year,
                'enddate': enddate,
                'includeopen': includeopen,
            },
            1
        )
        title = 'Results report'
        totalname = 'Final result'
        valheaders = ['Amount']
    elif reporttype == 'balance':
        # Balance report.
        # We always assume we have an incoming balance and that the previous
        # year has been closed. If it's not closed, we just show a warning
        # about that.
        try:
            prevyear = Year.objects.get(year=year.year - 1)
            if prevyear and prevyear.isopen:
                messages.warning(request, 'Previous year (%s) is still open. Incoming balance will be incorrect!' % prevyear.year)
        except Year.DoesNotExist:
            pass

        if includeopen:
            valheaders = ['Incoming', 'Period', 'Open', 'Period+Open', 'Outgoing']
        else:
            valheaders = ['Incoming', 'Period', 'Outgoing']
        (results, totalresult) = _collate_results(
            _get_balance_query(objstr, includeopen), {
                'year': year.year,
                'enddate': enddate,
            },
            len(valheaders)
        )
        title = 'Balance report'
        totalname = 'Final balance'
    elif reporttype == 'object':
        if not object:
            raise Http404("Object report requires object")

        # Hasopenentries now need to reflect if this *object* has any open entries
        hasopenentries = JournalEntry.objects.filter(journalitem__object=object, closed=False).exists()

        # Note! Probably sync up much of this query with the results report!
        (results, totalresult) = _collate_results(
            """WITH t AS (
SELECT ac.name as acname,
       ag.name as agname,
       ag.foldable,
       a.num as anum,
       a.name,
       sum(-ji.amount) as amount
FROM accounting_accountclass ac
INNER JOIN accounting_accountgroup ag ON ac.id=ag.accountclass_id
INNER JOIN accounting_account a ON ag.id=a.group_id
INNER JOIN accounting_journalitem ji ON ji.account_id=a.num
INNER JOIN accounting_journalentry je ON je.id=ji.journal_id
WHERE (je.closed or %(includeopen)s)
  AND NOT ac.inbalance {0}
GROUP BY ac.name, ag.name, ag.foldable, a.id, a.name
)
SELECT acname,
       agname,
       anum,
       name,
       count(*) OVER (PARTITION BY agname) = 1 AND foldable as agfold,
       sum(amount) OVER (PARTITION by acname) AS acamount,
       sum(amount) OVER (PARTITION by agname) AS agamount,
       amount,
       sum(amount) OVER ()
FROM t
ORDER BY anum""".format(objstr),
            {
                'year': year.year,
                'enddate': enddate,
                'includeopen': includeopen,
            },
            1
        )
        title = '{0} result report'.format(object.name)
        totalname = 'Final result for {0}'.format(object.name)
        valheaders = ['Amount']

        curs = connection.cursor()
        curs.execute("SELECT min(date), max(date) FROM accounting_journalentry e WHERE EXISTS (SELECT 1 FROM accounting_journalitem i WHERE i.object_id=%(object)s AND i.journal_id=e.id)", {
            'object': object.id,
        })
        (mindate, maxdate) = curs.fetchone()

        suppress_years = True
    else:
        raise Http404("Unknown report")

    # XXX: PDF maybe?
    return render(request, 'accounting/yearreports.html', {
        'reporttype': reporttype,
        'title': title,
        'year': year and year or -1,
        'years': years,
        'reportable_objects': filtered_objects,
        'hasopenentries': hasopenentries,
        'results': results,
        'totalresult': totalresult,
        'valheaders': valheaders,
        'totalname': totalname,
        'currentobj': object,
        'enddate': enddate,
        'mindate': mindate,
        'maxdate': maxdate,
        'includeopen': includeopen,
        'yearsuffix': 'report/{}/'.format(reporttype),
        'isreport': True,
        'suppress_years': suppress_years,
    })
