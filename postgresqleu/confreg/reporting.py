from django.shortcuts import render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.db import connection

from postgresqleu.confreg.models import ConferenceSeries

# XXX: How to handle timezones when two different conferences are involved (in time reports)?
# XXX: Probably need to show the timezone on the output as well somehow!


class ReportException(Exception):
    pass


class Header(object):
    def __init__(self, hdr):
        self.hdr = hdr

    def __str__(self):
        return self.hdr


@login_required
def timereport(request):
    if not (request.user.is_superuser or ConferenceSeries.objects.filter(administrators=request.user).exists()):
        return HttpResponseForbidden()

    from .reportingforms import TimeReportForm
    if request.method == 'POST':
        form = TimeReportForm(request.user, data=request.POST)
        if form.is_valid():
            reporttype = int(form.cleaned_data['reporttype'])
            conferences = form.cleaned_data['conferences']
            trendlines = form.cleaned_data['trendline']

            report = None
            try:
                report = reporttypes[reporttype - 1][1](reporttypes[reporttype - 1][0], conferences)
                report.run()
                return render(request, 'confreg/timereport.html', {
                    'form': form,
                    'title': report.title,
                    'ylabel': report.ylabel,
                    'xlabel': 'Days',
                    'series': report.series,
                    'dayvals': report.dayvals,
                    'trendlines': report.does_trendlines and trendlines,
                    'helplink': 'reports#time',
                    })
            except ReportException as e:
                messages.error(request, e)
                return render(request, 'confreg/timereport.html', {
                    'form': form,
                    })
    else:
        form = TimeReportForm(request.user)

    return render(request, 'confreg/timereport.html', {
        'form': form,
        'helplink': 'reports#time',
        })


# Dynamically built list of all available report types
reporttypes = []


# ##########################################################3
# Base classes for reports
# ##########################################################3
class MultiConferenceReport(object):
    def __init__(self, title, ylabel, conferences):
        self.title = title
        self.ylabel = ylabel
        self.conferences = conferences
        self.does_trendlines = True
        self.curs = connection.cursor()
        self.series = []

    def run(self):
        (maxday, minday) = self.maxmin()
        if not maxday:
            raise ReportException("There are no %s at this conference." % self.title.lower())
        self.dayvals = list(range(maxday, minday - 1 if minday <= 0 else -1, -1))
        for c in self.conferences:
            myvals = [r[0] for r in self.fetch_all_data(c, minday, maxday)]
            self.series.append({
                'label': c.conferencename,
                'values': myvals,
            })


class SingleConferenceReport(object):
    def __init__(self, title, conferences):
        self.title = title
        self.ylabel = 'Number of registrations'
        self.does_trendlines = False

        if len(conferences) != 1:
            raise ReportException('For this report type you must pick a single conference')
        self.conference = conferences[0]
        self.curs = connection.cursor()
        self.series = []

    def maxmin(self):
        self.curs.execute("SELECT max(startdate-payconfirmedat::date), min(startdate-payconfirmedat::date),max(startdate) FROM confreg_conferenceregistration r INNER JOIN confreg_conference c ON r.conference_id=c.id WHERE r.conference_id=%(id)s AND r.payconfirmedat IS NOT NULL", {
            'id': self.conference.id
        })
        return self.curs.fetchone()

    def run(self):
        (maxday, minday, startdate) = self.maxmin()
        if not maxday:
            raise ReportException("There are no %s at this conference." % self.title.lower())
        self.dayvals = list(range(maxday, minday - 1, -1))
        for header, rows in self.fetch_all_data(minday, maxday, startdate):
            self.series.append({
                'label': header,
                'values': [r[0] for r in rows],
            })


# ##########################################################3
# Actually report classes
# ##########################################################3
class ConfirmedRegistrationsReport(MultiConferenceReport):
    def __init__(self, title, conferences):
        super(ConfirmedRegistrationsReport, self).__init__(title, 'Number of registrations', conferences)

    def maxmin(self):
        self.curs.execute("SELECT max(startdate-payconfirmedat::date), min(startdate-payconfirmedat::date) FROM confreg_conference c INNER JOIN confreg_conferenceregistration r ON c.id=r.conference_id WHERE c.id=ANY(%(idlist)s) AND r.payconfirmedat IS NOT NULL AND r.canceledat IS NULL", {'idlist': [c.id for c in self.conferences]})
        return self.curs.fetchone()

    def fetch_all_data(self, conference, min, max):
        self.curs.execute("WITH t AS (SELECT startdate-payconfirmedat::date AS d, count(*) AS num FROM confreg_conferenceregistration r INNER JOIN confreg_conference c ON c.id=r.conference_id WHERE c.id=%(id)s AND r.payconfirmedat IS NOT NULL AND r.canceledat IS NULL GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
            'id': conference.id,
            'min': min,
            'max': max,
        })
        return self.curs.fetchall()


reporttypes.append(('Confirmed registrations', ConfirmedRegistrationsReport))


class CanceledRegistrationsReport(MultiConferenceReport):
    def __init__(self, title, conferences):
        super(CanceledRegistrationsReport, self).__init__(title, 'Number of registrations', conferences)

    def maxmin(self):
        self.curs.execute("SELECT max(startdate-canceledat::date), min(startdate-canceledat::date) FROM confreg_conference c INNER JOIN confreg_conferenceregistration r ON c.id=r.conference_id WHERE c.id=ANY(%(idlist)s) AND r.payconfirmedat IS NOT NULL AND r.canceledat IS NOT NULL", {'idlist': [c.id for c in self.conferences]})
        return self.curs.fetchone()

    def fetch_all_data(self, conference, min, max):
        self.curs.execute("WITH t AS (SELECT startdate-canceledat::date AS d, count(*) AS num FROM confreg_conferenceregistration r INNER JOIN confreg_conference c ON c.id=r.conference_id WHERE c.id=%(id)s AND r.payconfirmedat IS NOT NULL AND r.canceledat IS NOT NULL GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
            'id': conference.id,
            'min': min,
            'max': max,
        })
        return self.curs.fetchall()


reporttypes.append(('Canceled registrations', CanceledRegistrationsReport))


class RegistrationsAndCancelesReport(SingleConferenceReport):
    def maxmin(self):
        self.curs.execute("SELECT max(greatest(startdate-payconfirmedat::date, startdate-canceledat::date)), min(least(startdate-payconfirmedat::date, startdate-canceledat::date)),max(startdate) FROM confreg_conferenceregistration r INNER JOIN confreg_conference c ON r.conference_id=c.id WHERE r.conference_id=%(id)s AND r.payconfirmedat IS NOT NULL", {
            'id': self.conference.id
        })
        return self.curs.fetchone()

    def fetch_all_data(self, min, max, startdate):
        self.curs.execute("WITH t AS (SELECT %(startdate)s-payconfirmedat::date AS d, count(*) AS num FROM confreg_conferenceregistration r WHERE r.conference_id=%(cid)s AND r.payconfirmedat IS NOT NULL GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
            'cid': self.conference.id,
            'min': min,
            'max': max,
            'startdate': startdate,
        })
        yield ('Confirmed', self.curs.fetchall())

        self.curs.execute("WITH t AS (SELECT %(startdate)s-canceledat::date AS d, count(*) AS num FROM confreg_conferenceregistration r WHERE r.conference_id=%(cid)s AND r.payconfirmedat IS NOT NULL AND r.canceledat IS NOT NULL GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
            'cid': self.conference.id,
            'min': min,
            'max': max,
            'startdate': startdate,
        })
        yield ('Canceled', self.curs.fetchall())


reporttypes.append(('Registrations and cancels', RegistrationsAndCancelesReport))


class SubmittedSessionsReport(MultiConferenceReport):
    def __init__(self, title, conferences):
        super(SubmittedSessionsReport, self).__init__(title, 'Number of sessions', conferences)

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


class SubmittingSpeakersReport(MultiConferenceReport):
    def __init__(self, title, conferences):
        super(SubmittingSpeakersReport, self).__init__(title, 'Number of speakers', conferences)

    def maxmin(self):
        self.curs.execute("SELECT max(extract(days from startdate-initialsubmit)::integer), min(extract(days from startdate-initialsubmit)::integer) FROM confreg_conference c INNER JOIN confreg_conferencesession s ON c.id=s.conference_id WHERE c.id=ANY(%(idlist)s) AND s.initialsubmit IS NOT NULL AND NOT s.cross_schedule", {'idlist': [c.id for c in self.conferences]})
        return self.curs.fetchone()

    def fetch_all_data(self, conference, min, max):
        self.curs.execute("WITH t AS (SELECT extract(days from startdate-initialsubmit) AS d, count(distinct speaker_id) AS num FROM confreg_conferencesession s INNER JOIN confreg_conference c ON c.id=s.conference_id INNER JOIN confreg_conferencesession_speaker spk ON s.id=spk.conferencesession_id WHERE c.id=%(id)s AND s.initialsubmit IS NOT NULL AND NOT s.cross_schedule GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
            'id': conference.id,
            'min': min,
            'max': max,
        })
        return self.curs.fetchall()


reporttypes.append(('Submitting speakers', SubmittingSpeakersReport))


class ConfirmedSponsorsReport(MultiConferenceReport):
    def __init__(self, title, conferences):
        super(ConfirmedSponsorsReport, self).__init__(title, 'Confirmed sponsors', conferences)

    def maxmin(self):
        self.curs.execute("SELECT max(extract(days FROM startdate-confirmedat)::integer), min(extract(days FROM startdate-confirmedat)::integer) FROM confreg_conference c INNER JOIN confsponsor_sponsor s ON c.id=s.conference_id WHERE c.id=ANY(%(idlist)s) AND confirmedat IS NOT NULL", {'idlist': [c.id for c in self.conferences]})
        return self.curs.fetchone()

    def fetch_all_data(self, conference, min, max):
        self.curs.execute("WITH t AS (SELECT extract(days FROM startdate-confirmedat)::integer AS d, count(*) AS num FROM confreg_conference c INNER JOIN confsponsor_sponsor s ON c.id=s.conference_id WHERE c.id=%(id)s AND confirmedat IS NOT NULL GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series(%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC)::integer, 0) FROM tt ORDER BY g DESC", {
            'id': conference.id,
            'min': min,
            'max': max,
        })
        return self.curs.fetchall()


reporttypes.append(('Confirmed sponsors', ConfirmedSponsorsReport))


class SponsorLevelsReport(SingleConferenceReport):
    def maxmin(self):
        self.curs.execute("SELECT max(extract(days FROM startdate-confirmedat)::integer)+1, min(extract(days FROM startdate-confirmedat)::integer), max(startdate) FROM confreg_conference c INNER JOIN confsponsor_sponsor s ON c.id=s.conference_id WHERE c.id=%(id)s AND confirmedat IS NOT NULL", {
            'id': self.conference.id
        })
        return self.curs.fetchone()

    def fetch_all_data(self, min, max, startdate):
        self.curs.execute("SELECT id, levelname FROM confsponsor_sponsorshiplevel l WHERE l.conference_id=%(id)s AND EXISTS (SELECT 1 FROM confsponsor_sponsor s WHERE s.level_id=l.id AND confirmedat IS NOT NULL AND s.conference_id=%(id)s)", {
            'id': self.conference.id,
        })
        for levelid, levelname in self.curs.fetchall():
            self.curs.execute("WITH t AS (SELECT %(startdate)s-confirmedat::date AS d, count(*) AS num FROM confsponsor_sponsor s WHERE s.conference_id=%(cid)s AND s.confirmedat IS NOT NULL AND s.level_id=%(lid)s GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series(%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC), 0)::integer FROM tt ORDER BY g DESC", {
                'cid': self.conference.id,
                'min': min,
                'max': max,
                'lid': levelid,
                'startdate': startdate,
            })
            yield (levelname, self.curs.fetchall())


reporttypes.append(('Sponsor levels', SponsorLevelsReport))


class RegistrationTypesReport(SingleConferenceReport):
    def fetch_all_data(self, min, max, startdate):
        self.curs.execute("SELECT id, regtype FROM confreg_registrationtype rt WHERE EXISTS (SELECT * FROM confreg_conferenceregistration r WHERE r.regtype_id=rt.id AND r.payconfirmedat IS NOT NULL AND r.conference_id=%(id)s)", {
            'id': self.conference.id,
        })
        for regid, regtype in self.curs.fetchall():
            self.curs.execute("WITH t AS (SELECT %(startdate)s-payconfirmedat::date AS d, count(*) AS num FROM confreg_conferenceregistration r WHERE r.conference_id=%(cid)s AND r.payconfirmedat IS NOT NULL AND r.regtype_id=%(rid)s GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
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
        self.curs.execute("SELECT DISTINCT country_id FROM confreg_conferenceregistration r WHERE r.payconfirmedat IS NOT NULL AND r.conference_id=%(id)s AND country_id IS NOT NULL", {
            'id': self.conference.id,
        })
        for countryid, in self.curs.fetchall():
            self.curs.execute("WITH t AS (SELECT %(startdate)s-payconfirmedat::date AS d, count(*) AS num FROM confreg_conferenceregistration r WHERE r.conference_id=%(cid)s AND r.payconfirmedat IS NOT NULL AND r.country_id=%(country)s GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
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
            self.curs.execute("WITH t AS (SELECT startdate-payconfirmedat::date AS d, count(*) AS num FROM confreg_conferenceregistration r INNER JOIN confreg_conference c ON c.id=r.conference_id INNER JOIN confreg_conferenceregistration_additionaloptions rao ON rao.conferenceregistration_id=r.id WHERE c.id=%(cid)s AND r.payconfirmedat IS NOT NULL AND rao.conferenceadditionaloption_id=%(aoid)s GROUP BY d), tt AS (SELECT g.g, num FROM t RIGHT JOIN generate_series (%(min)s, %(max)s) g(g) ON g.g=t.d) SELECT COALESCE(sum(num) OVER (ORDER BY g DESC),0)::integer FROM tt ORDER BY g DESC", {
                'cid': self.conference.id,
                'min': min,
                'max': max,
                'aoid': optionid,
                'startdate': startdate,
            })
            yield (optionname, self.curs.fetchall())


reporttypes.append(('Additional options', AdditionalOptionsReport))
