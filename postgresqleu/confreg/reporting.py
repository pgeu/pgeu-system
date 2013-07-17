from django.shortcuts import render_to_response
from django.template import RequestContext
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import connection

from postgresqleu.util.decorators import user_passes_test_or_error, ssl_required

from datetime import datetime

class ReportException(Exception):
	pass

class Header(object):
	def __init__(self, hdr, hastoday):
		self.hdr = hdr
		self.hastoday = hastoday

	def __unicode__(self):
		return self.hdr

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.is_superuser)
def timereport(request):
	from reportingforms import TimeReportForm
	if request.method == 'POST':
		form = TimeReportForm(data=request.POST)
		if form.is_valid():
			reporttype = int(form.cleaned_data['reporttype'])
			conferences = form.cleaned_data['conferences']

			report = None
			try:
				report = reporttypes[reporttype-1][1](reporttypes[reporttype-1][0],conferences)
				report.run()
				return render_to_response('confreg/timereport.html', {
					'form': form,
					'title': report.title,
					'ylabel': report.ylabel,
					'headers': report.headers,
					'graphdata': report.graphdata,
					}, context_instance=RequestContext(request))
			except ReportException, e:
				messages.error(request, e)
				return render_to_response('confreg/timereport.html', {
					'form': form,
					}, context_instance=RequestContext(request))
	else:
		form = TimeReportForm()

	return render_to_response('confreg/timereport.html', {
		'form': form,
		}, context_instance=RequestContext(request))


# Dynamically built list of all available report types
reporttypes = []

###########################################################3
# Base classes for reports
###########################################################3
class MultiConferenceReport(object):
	def __init__(self, title, ylabel, conferences):
		self.title = title
		self.ylabel = ylabel
		self.conferences = conferences
		self.headers = None
		self.curs = connection.cursor()

	def run(self):
		(max,min) = self.maxmin()
		if not max:
			raise ReportException("There are no %s at this conference." % self.title.lower())
		if min > 0: min = 0
		allvals = [range(max, min-1, -1), ]
		self.headers = ['Days']
		for c in self.conferences:
			allvals.append([r[0] for r in self.fetch_all_data(c, min, max)])
			todaydaysago = (c.startdate-datetime.today().date()).days
			self.headers.append(Header(c.conferencename, todaydaysago in allvals[0]))
			if todaydaysago in allvals[0]:
				allvals.append([(r >= todaydaysago) and 'true' or 'false' for r in allvals[0]])

		self.graphdata = zip(*allvals)

class SingleConferenceReport(object):
	def __init__(self, title, conferences):
		self.title = title
		self.ylabel = 'Number of registrations'

		if len(conferences) != 1:
			raise ReportException('For this report type you must pick a single conference')
		self.conference = conferences[0]
		self.headers = None
		self.curs = connection.cursor()

	def run(self):
		self.curs.execute("SELECT max(startdate-payconfirmedat), min(startdate-payconfirmedat),max(startdate) FROM confreg_conferenceregistration r INNER JOIN confreg_conference c ON r.conference_id=c.id WHERE r.conference_id=%(id)s AND r.payconfirmedat IS NOT NULL", {
			'id': self.conference.id
		})
		(max,min,startdate) = self.curs.fetchone()
		if not max:
			raise ReportException('There are no confirmed registrations at this conference.')
		todaydaysago = (startdate-datetime.today().date()).days
		if min > 0: min = 0
		allvals = [range(max,min-1,-1), ]
		hasfuture = todaydaysago in allvals[0]
		self.headers = ['Days']
		for header, rows in self.fetch_all_data(min, max, startdate):
			allvals.append([r[0] for r in rows])
			self.headers.append(Header(header, hasfuture))
			if hasfuture:
				allvals.append([(r >= todaydaysago) and 'true' or 'false' for r in allvals[0]])
		self.graphdata = zip(*allvals)


###########################################################3
# Actually report classes
###########################################################3
class ConfirmedRegistrationsReport(MultiConferenceReport):
	def __init__(self, title, conferences):
		super(ConfirmedRegistrationsReport, self).__init__(title,'Number of registrations',conferences)

	def maxmin(self):
		self.curs.execute("SELECT max(startdate-payconfirmedat), min(startdate-payconfirmedat) FROM confreg_conference c INNER JOIN confreg_conferenceregistration r ON c.id=r.conference_id WHERE c.id=ANY(%(idlist)s) AND r.payconfirmedat IS NOT NULL", {'idlist': [c.id for c in self.conferences]})
		return self.curs.fetchone()

	def fetch_all_data(self, conference, min, max):
		self.curs.execute("WITH t AS (SELECT startdate-payconfirmedat AS d, count(*) AS num FROM confreg_conferenceregistration r INNER JOIN confreg_conference c ON c.id=r.conference_id WHERE c.id=%(id)s AND r.payconfirmedat IS NOT NULL GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
			'id': conference.id,
			'min': min,
			'max': max,
		})
		return self.curs.fetchall()
reporttypes.append(('Confirmed registrations', ConfirmedRegistrationsReport))

class SubmittedSessionsReport(MultiConferenceReport):
	def __init__(self, title, conferences):
		super(SubmittedSessionsReport, self).__init__(title,'Number of sessions',conferences)

	def maxmin(self):
		self.curs.execute("SELECT max(extract(days from startdate-initialsubmit)::integer), min(extract(days from startdate-initialsubmit)::integer) FROM confreg_conference c INNER JOIN confreg_conferencesession s ON c.id=s.conference_id WHERE c.id=ANY(%(idlist)s) AND s.initialsubmit IS NOT NULL AND NOT s.cross_schedule", {'idlist': [c.id for c in self.conferences]})
		return self.curs.fetchone()

	def fetch_all_data(self, conference, min, max):
		self.curs.execute("WITH t AS (SELECT extract(days from startdate-initialsubmit) AS d, count(*) AS num FROM confreg_conferencesession s INNER JOIN confreg_conference c ON c.id=s.conference_id WHERE c.id=%(id)s AND s.initialsubmit IS NOT NULL AND NOT s.cross_schedule GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
			'id': conference.id,
			'min': min,
			'max': max,
		})
		return self.curs.fetchall()
reporttypes.append(('Submitted sessions', SubmittedSessionsReport))

class RegistrationTypesReport(SingleConferenceReport):
	def fetch_all_data(self, min, max, startdate):
		self.curs.execute("SELECT id, regtype FROM confreg_registrationtype rt WHERE EXISTS (SELECT * FROM confreg_conferenceregistration r WHERE r.regtype_id=rt.id AND r.payconfirmedat IS NOT NULL AND r.conference_id=%(id)s)", {
			'id': self.conference.id,
		})
		for regid, regtype in self.curs.fetchall():
			self.curs.execute("WITH t AS (SELECT %(startdate)s-payconfirmedat AS d, count(*) AS num FROM confreg_conferenceregistration r WHERE r.conference_id=%(cid)s AND r.payconfirmedat IS NOT NULL AND r.regtype_id=%(rid)s GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
				'cid': self.conference.id,
				'min': min,
				'max': max,
				'rid': regid,
				'startdate': startdate,
			})
			yield (regtype, self.curs.fetchall())
reporttypes.append(('Registration types', RegistrationTypesReport))

class CountryReport(SingleConferenceReport):
	def fetch_all_data(self, min, max, startdate):
		self.curs.execute("SELECT DISTINCT country_id FROM confreg_conferenceregistration r WHERE r.payconfirmedat IS NOT NULL AND r.conference_id=%(id)s", {
			'id': self.conference.id,
		})
		for countryid, in self.curs.fetchall():
			self.curs.execute("WITH t AS (SELECT %(startdate)s-payconfirmedat AS d, count(*) AS num FROM confreg_conferenceregistration r WHERE r.conference_id=%(cid)s AND r.payconfirmedat IS NOT NULL AND r.country_id=%(country)s GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
				'cid': self.conference.id,
				'min': min,
				'max': max,
				'country': countryid,
				'startdate': startdate,
			})
			yield (countryid, self.curs.fetchall())
reporttypes.append(('Countries', CountryReport))

class AdditionalOptionsReport(SingleConferenceReport):
	def fetch_all_data(self, min, max, startdate):
		self.curs.execute("SELECT DISTINCT id, name FROM confreg_conferenceadditionaloption ao WHERE conference_id=%(id)s", {
			'id': self.conference.id,
		})
		for optionid, optionname in self.curs.fetchall():
			self.curs.execute("WITH t AS (SELECT startdate-payconfirmedat AS d, count(*) AS num FROM confreg_conferenceregistration r INNER JOIN confreg_conference c ON c.id=r.conference_id INNER JOIN confreg_conferenceregistration_additionaloptions rao ON rao.conferenceregistration_id=r.id WHERE c.id=%(cid)s AND r.payconfirmedat IS NOT NULL AND rao.conferenceadditionaloption_id=%(aoid)s GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
				'cid': self.conference.id,
				'min': min,
				'max': max,
				'aoid': optionid,
				'startdate': startdate,
			})
			yield (optionname, self.curs.fetchall())
reporttypes.append(('Additional options', AdditionalOptionsReport))
