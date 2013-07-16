from django.shortcuts import render_to_response
from django.template import RequestContext
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import connection

from postgresqleu.util.decorators import user_passes_test_or_error, ssl_required
from reportingforms import TimeReportForm

class ReportException(Exception):
	pass

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.is_superuser)
def timereport(request):
	title = None
	ylabel = None
	headers = None
	graphdata = None
	if request.method == 'POST':
		form = TimeReportForm(data=request.POST)
		if form.is_valid():
			reporttype = int(form.cleaned_data['reporttype'])
			conferences = form.cleaned_data['conferences']
			curs = connection.cursor()

			try:
				# These different reports can probably be factored out into
				# some more common functionality, but for now, just rewrite
				# the queries for each one with small differences..
				if reporttype == 1:
					# Confirmed registrations
					curs.execute("SELECT max(startdate-payconfirmedat), min(startdate-payconfirmedat) FROM confreg_conference c INNER JOIN confreg_conferenceregistration r ON c.id=r.conference_id WHERE c.id=ANY(%(idlist)s) AND r.payconfirmedat IS NOT NULL", {
						'idlist': [c.id for c in conferences],
						})
					(max,min) = curs.fetchone()
					if not max:
						raise ReportException('There are no confirmed registrations at this conference.')
					if min > 0: min = 0
					allvals = [range(max,min-1,-1), ]
					headers = ['Days']
					# Now fetch the values for each conference. We could perhaps
					# do it in one query, but are too lazy.
					for c in conferences:
						curs.execute("WITH t AS (SELECT startdate-payconfirmedat AS d, count(*) AS num FROM confreg_conferenceregistration r INNER JOIN confreg_conference c ON c.id=r.conference_id WHERE c.id=%(id)s AND r.payconfirmedat IS NOT NULL GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
							'id': c.id,
							'min': min,
							'max': max,
							})
						allvals.append([r[0] for r in curs.fetchall()])
						headers.append(c.conferencename)
					graphdata = zip(*allvals)
					title = 'Confirmed registrations'
					ylabel = 'Number of registrations'
				elif reporttype== 2:
					# Submissions
					curs.execute("SELECT max(extract(days from startdate-initialsubmit)::integer), min(extract(days from startdate-initialsubmit)::integer) FROM confreg_conference c INNER JOIN confreg_conferencesession s ON c.id=s.conference_id WHERE c.id=ANY(%(idlist)s) AND s.initialsubmit IS NOT NULL AND NOT s.cross_schedule", {
						'idlist': [c.id for c in conferences],
						})
					(max,min) = curs.fetchone()
					if not max:
						raise ReportException('There are no submitted sessions for this conference.')
					if min > 0: min = 0
					allvals = [range(max,min-1,-1), ]
					headers = ['Days']
					# Now fetch the values for each conference. We could perhaps
					# do it in one query, but are too lazy.
					for c in conferences:
						curs.execute("WITH t AS (SELECT extract(days from startdate-initialsubmit) AS d, count(*) AS num FROM confreg_conferencesession s INNER JOIN confreg_conference c ON c.id=s.conference_id WHERE c.id=%(id)s AND s.initialsubmit IS NOT NULL AND NOT s.cross_schedule GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
							'id': c.id,
							'min': min,
							'max': max,
							})
						allvals.append([r[0] for r in curs.fetchall()])
						headers.append(c.conferencename)
					graphdata = zip(*allvals)
					title = 'Conference submissions'
					ylabel = 'Number of submissions'
				elif reporttype==3:
					# Registration types
					if len(conferences) != 1:
						raise ReportException('For this report type you must pick a single conference')
					cid = conferences[0].id
					curs.execute("SELECT max(startdate-payconfirmedat), min(startdate-payconfirmedat),max(startdate) FROM confreg_conferenceregistration r INNER JOIN confreg_conference c ON r.conference_id=c.id WHERE r.conference_id=%(id)s AND r.payconfirmedat IS NOT NULL", {
						'id': cid,
						})
					(max,min,startdate) = curs.fetchone()
					if not max:
						raise ReportException('There are no confirmed registrations at this conference.')
					if min > 0: min = 0
					allvals = [range(max,min-1,-1), ]
					headers = ['Days']
					# Could do crosstab, but I'm lazy
					curs.execute("SELECT id, regtype FROM confreg_registrationtype rt WHERE EXISTS (SELECT * FROM confreg_conferenceregistration r WHERE r.regtype_id=rt.id AND r.payconfirmedat IS NOT NULL AND r.conference_id=%(id)s)", {
						'id': cid,
					})
					for regid, regtype in curs.fetchall():
						curs.execute("WITH t AS (SELECT %(startdate)s-payconfirmedat AS d, count(*) AS num FROM confreg_conferenceregistration r WHERE r.conference_id=%(cid)s AND r.payconfirmedat IS NOT NULL AND r.regtype_id=%(rid)s GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
							'cid': cid,
							'min': min,
							'max': max,
							'rid': regid,
							'startdate': startdate,
						})
						allvals.append([r[0] for r in curs.fetchall()])
						headers.append(regtype)
					graphdata = zip(*allvals)
					title = 'Confirmed registrations'
					ylabel = 'Number of registrations'
				elif reporttype==4:
					# Countries
					if len(conferences) != 1:
						raise ReportException('For this report type you must pick a single conference')
					cid = conferences[0].id
					curs.execute("SELECT max(startdate-payconfirmedat), min(startdate-payconfirmedat),max(startdate) FROM confreg_conferenceregistration r INNER JOIN confreg_conference c ON r.conference_id=c.id WHERE r.conference_id=%(id)s AND r.payconfirmedat IS NOT NULL", {
						'id': cid,
						})
					(max,min,startdate) = curs.fetchone()
					if not max:
						raise ReportException('There are no confirmed registrations at this conference.')
					if min > 0: min = 0
					allvals = [range(max,min-1,-1), ]
					headers = ['Days']
					# Could do crosstab, but I'm lazy
					curs.execute("SELECT DISTINCT country_id FROM confreg_conferenceregistration r WHERE r.payconfirmedat IS NOT NULL AND r.conference_id=%(id)s", {
						'id': cid,
					})
					for countryid, in curs.fetchall():
						curs.execute("WITH t AS (SELECT %(startdate)s-payconfirmedat AS d, count(*) AS num FROM confreg_conferenceregistration r WHERE r.conference_id=%(cid)s AND r.payconfirmedat IS NOT NULL AND r.country_id=%(country)s GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
							'cid': cid,
							'min': min,
							'max': max,
							'country': countryid,
							'startdate': startdate,
						})
						allvals.append([r[0] for r in curs.fetchall()])
						headers.append(countryid)
					graphdata = zip(*allvals)
					title = 'Confirmed registrations'
					ylabel = 'Number of registrations'
				elif reporttype==5:
					# Additional options
					if len(conferences) != 1:
						raise ReportException('For this report type you must pick a single conference')
					cid = conferences[0].id
					curs.execute("SELECT max(startdate-payconfirmedat), min(startdate-payconfirmedat),max(startdate) FROM confreg_conferenceregistration r INNER JOIN confreg_conference c ON r.conference_id=c.id WHERE r.conference_id=%(id)s AND r.payconfirmedat IS NOT NULL", {
						'id': cid,
						})
					(max,min,startdate) = curs.fetchone()
					if not max:
						raise ReportException('There are no confirmed registrations at this conference.')
					if min > 0: min = 0
					allvals = [range(max,min-1,-1), ]
					headers = ['Days']
					# Could do crosstab, but I'm lazy
					curs.execute("SELECT DISTINCT id, name FROM confreg_conferenceadditionaloption ao WHERE conference_id=%(id)s", {
						'id': cid,
					})
					for optionid, optionname in curs.fetchall():
						curs.execute("WITH t AS (SELECT startdate-payconfirmedat AS d, count(*) AS num FROM confreg_conferenceregistration r INNER JOIN confreg_conference c ON c.id=r.conference_id INNER JOIN confreg_conferenceregistration_additionaloptions rao ON rao.conferenceregistration_id=r.id WHERE c.id=%(id)s AND r.payconfirmedat IS NOT NULL AND rao.conferenceadditionaloption_id=%(aoid)s GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
							'id': cid,
							'min': min,
							'max': max,
							'aoid': optionid,
							})
						allvals.append([r[0] for r in curs.fetchall()])
						headers.append(optionname)
					graphdata = zip(*allvals)
					title = 'Additional options'
					ylabel = 'Number of registrations'
				else:
					raise Exception("Cannot happen!")
			except ReportException, e:
				messages.error(request, e)
				return render_to_response('confreg/timereport.html', {
					'form': form,
					}, context_instance=RequestContext(request))
	else:
		form = TimeReportForm()

	return render_to_response('confreg/timereport.html', {
		'form': form,
		'title': title,
		'ylabel': ylabel,
		'headers': headers,
		'graphdata': graphdata,
		}, context_instance=RequestContext(request))
