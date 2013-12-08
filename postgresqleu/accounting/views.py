from django.http import HttpResponseRedirect, Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render_to_response, get_object_or_404
from django.template import RequestContext
from django.forms.models import inlineformset_factory
from django.db.models import Max, Q
from django.db import connection, transaction

from datetime import datetime, date

from postgresqleu.util.decorators import user_passes_test_or_error, ssl_required

from models import JournalEntry, JournalItem, Year, Object
from models import IncomingBalance, Account
from forms import JournalEntryForm, JournalItemForm, JournalItemFormset

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('accounting'))
def index(request):
	# Always redirect to the current year
	return HttpResponseRedirect("%s/" % datetime.today().year)


def _setup_search(request, term):
	if term:
		request.session['searchterm'] = term
	else:
		if request.session.has_key('searchterm'):
			del request.session['searchterm']

def _perform_search(request, year):
	if request.session.has_key('searchterm'):
		searchterm = request.session['searchterm']
		return (searchterm,
				list(
					JournalEntry.objects.filter(year=year, journalitem__description__icontains=searchterm)
					.distinct().order_by('closed', '-date', '-id')))

	return ('', list(JournalEntry.objects.filter(year=year).order_by('closed', '-date', '-id')))

@ssl_required
@login_required
@transaction.commit_on_success
@user_passes_test_or_error(lambda u: u.has_module_perms('accounting'))
def year(request, year):
	year = get_object_or_404(Year, year=int(year))
	if request.GET.has_key('search'):
		_setup_search(request, request.GET['search'])
		return HttpResponseRedirect('/accounting/%s/' % year.year)


	(searchterm, entries) = _perform_search(request, year)

	return render_to_response('accounting/main.html', {
		'entries': entries,
		'hasopen': any([not e.closed for e in entries]),
		'year': year,
		'years': Year.objects.all(),
		'searchterm': searchterm,
		})

@ssl_required
@login_required
@transaction.commit_on_success
@user_passes_test_or_error(lambda u: u.has_module_perms('accounting'))
def new(request, year):
	year = int(year)
	if year == datetime.today().year:
		# This year, so use today
		d = datetime.today()
	elif year > datetime.today().year:
		# Viewing a year in the future, so set it to the beginning
		d = date(year, 1, 1)
	else:
		# Viewing a year in the past, so set it to the end
		d = date(year, 12, 31)
	year = get_object_or_404(Year, year=year)
	highseq = JournalEntry.objects.filter(year=year).aggregate(Max('seq'))['seq__max']
	if highseq is None:
		highseq = 0
	entry = JournalEntry(year=year, seq=highseq+1, date=d, closed=False)
	entry.save()

	# Disable any search query to make sure we can actually see
	# the record we've just created.
	_setup_search(request, '')

	return HttpResponseRedirect('/accounting/e/%s/' % entry.pk)

@ssl_required
@login_required
@transaction.commit_on_success
@user_passes_test_or_error(lambda u: u.has_module_perms('accounting'))
def entry(request, entryid):
	entry = get_object_or_404(JournalEntry, pk=entryid)

	if request.GET.has_key('search'):
		_setup_search(request, request.GET['search'])
		return HttpResponseRedirect('/accounting/e/%s/' % entryid)

	(searchterm, entries) = _perform_search(request, entry.year)

	extra = max(2, 6-entry.journalitem_set.count())
	inlineformset = inlineformset_factory(JournalEntry, JournalItem, JournalItemForm, JournalItemFormset, can_delete=True, extra=extra)

	if request.method == 'POST':
		if request.POST['submit'] == 'Delete':
			year = entry.year
			entry.delete()
			return HttpResponseRedirect("/accounting/%s/" % year.year)

		form = JournalEntryForm(data=request.POST, instance=entry)
		formset = inlineformset(data=request.POST, instance=entry)
		if form.is_valid():
			if formset.is_valid():
				instance = form.save()
				formset.save()

				if request.POST['submit'] == 'Close':
					instance.closed = True
					instance.save()
				return HttpResponseRedirect(".")
		# Else fall through
		print form.errors
	else:
		form = JournalEntryForm(instance=entry)
		formset = inlineformset(instance=entry)

	items = list(entry.journalitem_set.all())
	totals = (sum([i.amount for i in items if i.amount>0]),
			  -sum([i.amount for i in items if i.amount<0]))
	return render_to_response('accounting/main.html', {
		'entries': entries,
		'hasopen': any([not e.closed for e in entries]),
		'year': entry.year,
		'entry': entry,
		'items': items,
		'totals': totals,
		'form': form,
		'formset': formset,
		'years': Year.objects.all(),
		'searchterm': searchterm,
		})

def _get_balance_query(objstr=''):
	return """WITH currentyear AS (
 SELECT account_id AS accountnum, sum(amount) as amount FROM accounting_journalitem ji INNER JOIN accounting_journalentry je ON ji.journal_id=je.id WHERE je.year_id=%(year)s AND je.closed """ + objstr + """ GROUP BY account_id
), incoming AS (
 SELECT account_id AS accountnum, amount FROM accounting_incomingbalance WHERE year_id=%(year)s
), fullbalance AS (
SELECT coalesce(currentyear.accountnum, incoming.accountnum) as anum, coalesce(currentyear.amount,0) AS currentamount, coalesce(incoming.amount,0) AS incomingamount FROM currentyear FULL OUTER JOIN incoming ON currentyear.accountnum=incoming.accountnum
)
SELECT ac.name AS acname, ag.name AS agname, anum, a.name, sum(incomingamount) over (partition by ac.name) as acincoming, sum(currentamount) over (partition by ac.name) as accurrent, sum(incomingamount+currentamount) over (partition by ac.name) as acoutgoing, sum(incomingamount) over (partition by ag.name) as agincoming, sum(currentamount) over (partition by ag.name) as agcurrent, sum(incomingamount+currentamount) over (partition by ag.name) as agoutgoing, incomingamount, currentamount,incomingamount+currentamount as outgoingamount, sum(incomingamount*case when balancenegative then -1 else 1 end) over() as incomingtotal, sum(currentamount*case when balancenegative then -1 else 1 end) over () as currenttotal, sum((incomingamount+currentamount)*case when balancenegative then -1 else 1 end) over () as outgoingtotal FROM accounting_accountclass ac INNER JOIN accounting_accountgroup ag ON ac.id=ag.accountclass_id INNER JOIN accounting_account a ON ag.id=a.group_id INNER JOIN fullbalance ON fullbalance.anum=a.num WHERE ac.inbalance AND (incomingamount != 0 OR currentamount != 0) ORDER BY anum
		"""

def _collate_results(query, queryparam, numvalues):
	results = []
	lastag = ''
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

		acvals = row[:numvalues]
		row[:numvalues] = []
		agvals = row[:numvalues]
		row[:numvalues] = []
		avals = row[:numvalues]
		row[:numvalues] = []
		if not totalresult: totalresult = row[:numvalues]
		row[:numvalues] = []

		if len(row) != 0:
			raise Exception("Invalid number of entries left in row: %s" % len(row))

		if agname != lastag:
			if currentag:
				currentac.append([lastag, currentag, lastagvals])
				currentag = []
			lastag = agname
			lastagvals = agvals
		currentag.append([anum, aname, avals])

		if acname != lastac:
			if currentac:
				results.append([lastac, currentac, lastacvals])
				currentac = []
			lastac = acname
			lastacvals = acvals

	if currentag:
		currentac.append([lastag, currentag, lastagvals])
	if currentac:
		results.append([lastac, currentac, lastacvals])

	return (results, totalresult)

@ssl_required
@login_required
@transaction.commit_on_success
@user_passes_test_or_error(lambda u: u.has_module_perms('accounting'))
def closeyear(request, year):
	year = Year.objects.get(pk=year)
	hasopen = JournalEntry.objects.filter(year=year, closed=False).exists()
	try:
		nextyear = Year.objects.get(year=year.year+1)
		hasnext = IncomingBalance.objects.filter(year=nextyear).exists()
	except Year.DoesNotExist:
		hasnext = False

	curs = connection.cursor()
	curs.execute(_get_balance_query(), {
		'year': year.year,
		})
	balance = [dict(zip([col[0] for col in curs.description], row)) for row in curs.fetchall()]
	curs.execute("SELECT sum(-amount) FROM accounting_journalitem ji INNER JOIN accounting_journalentry je ON ji.journal_id=je.id INNER JOIN accounting_account a ON ji.account_id=a.num INNER JOIN accounting_accountgroup ag ON ag.id=a.group_id INNER JOIN accounting_accountclass ac ON ac.id=ag.accountclass_id WHERE je.year_id=%(year)s AND NOT inbalance", {
		'year': year.year,
	})
	yearresult = curs.fetchall()[0][0]

	if request.method == 'POST':
		if not request.POST.has_key('confirm') or not request.POST['confirm']:
			messages.warning(request, "You must check the box for confirming!")
		elif not request.POST['resultaccount']:
			messages.warning(request, "You must pick which account to post the results to!")
		else:
			# Ok, let's do this :)
			# Create a new year if we have to
			(nextyear, created) = Year.objects.get_or_create(year=year.year+1, defaults={'isopen':True})

			# Start by transferring this years result
			IncomingBalance(year=nextyear,
							account=Account.objects.get(num=request.POST['resultaccount']),
							amount=yearresult
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

	return render_to_response('accounting/closeyear.html', {
		'year': year,
		'hasopen': hasopen,
		'hasnext': hasnext,
		'outgoingbalance': balance,
		'yearresult': yearresult,
		'accounts': Account.objects.filter(group__accountclass__inbalance=True),
	}, context_instance=RequestContext(request))

@ssl_required
@login_required
@transaction.commit_on_success
@user_passes_test_or_error(lambda u: u.has_module_perms('accounting'))
def report(request, year, reporttype):
	year = get_object_or_404(Year, year=year)
	years = Year.objects.all()

	hasopenentries = JournalEntry.objects.filter(year=year, closed=False).exists()

	if year.isopen:
		messages.info(request, "This year is still open!")
	if hasopenentries:
		messages.warning(request, "This year has open entries! These are not included in the report!")

	if request.GET.has_key('obj') and request.GET['obj']:
		object = get_object_or_404(Object, pk=request.GET['obj'])
		objstr = "AND ji.object_id=%s" % object.id
	else:
		object = None
		objstr = ''

	if reporttype == 'ledger':
		# This is a special report, so we do our own return
		# XXX: This needs to be made smarter - summarize per account, and
		# consider perhaps including the in and out balance as well.
		itemfilter = Q(journal__year=year)
		if request.GET.has_key('obj') and request.GET['obj']:
			itemfilter = itemfilter & Q(object=object)
		items = JournalItem.objects.select_related().filter(itemfilter).order_by('account__num', 'journal__date', 'journal__seq')

		return render_to_response('accounting/ledgerreport.html', {
			'year': year,
			'years': years,
			'objects': Object.objects.all(),
			'currentobj': object,
			'reporttype': 'ledger',
			'items': items,
		}, context_instance=RequestContext(request))
	elif reporttype == 'results':
		# The results report is the easiest one, since we can assume that
		# all accounts enter the year with a value 0. Therefor, we only
		# care about summing the data for this year.
		# We only show accounts that have had some transactions on them.
		(results, totalresult) = _collate_results("WITH t AS (SELECT ac.name as acname, ag.name as agname, a.num as anum, a.name, sum(-ji.amount) as amount FROM accounting_accountclass ac INNER JOIN accounting_accountgroup ag ON ac.id=ag.accountclass_id INNER JOIN accounting_account a ON ag.id=a.group_id INNER JOIN accounting_journalitem ji ON ji.account_id=a.num INNER JOIN accounting_journalentry je ON je.id=ji.journal_id WHERE je.year_id=%(year)s AND je.closed AND NOT ac.inbalance " + objstr + " GROUP BY ac.name, ag.name, a.id, a.name) SELECT acname, agname, anum, name, sum(amount) over (partition by acname) as acamount, sum(amount) over (partition by agname) as agamount, amount, sum(amount) over () FROM t ORDER BY anum", {
			'year': year.year,
			},
												  1)
		title = 'Results report'
		totalname = 'Final result'
		valheaders = ['Amount']
	elif reporttype=='balance':
		# Balance report.
		# We always assume we have an incoming balance and that the previous
		# year has been closed. If it's not closed, we just show a warning
		# about that.
		try:
			prevyear = Year.objects.get(year=year.year-1)
			if prevyear and prevyear.isopen:
				messages.warning(request, 'Previous year (%s) is still open. Incoming balance will be incorrect!' % prevyear.year)
		except Year.DoesNotExist:
			pass

		(results, totalresult) = _collate_results(_get_balance_query(objstr), {
			'year': year.year,
		},
												   3)
		title = 'Balance report'
		totalname = 'Final balance'
		valheaders = ['Incoming', 'Period', 'Outgoing']
	else:
		raise Http404("Unknown report")

	# XXX: PDF maybe?
	return render_to_response('accounting/yearreports.html', {
		'reporttype': reporttype,
		'title': title,
		'year': year,
		'years': years,
		'hasopenentries': hasopenentries,
		'results': results,
		'totalresult': totalresult,
		'valheaders': valheaders,
		'totalname': totalname,
		'objects': Object.objects.all(),
		'currentobj': object,
	}, context_instance=RequestContext(request))
