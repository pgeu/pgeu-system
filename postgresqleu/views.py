# Index has a very special view that lives out here
from django.shortcuts import render, get_object_or_404

from postgresqleu.newsevents.models import News
from postgresqleu.confreg.models import Conference, ConferenceSeries

import datetime

# Handle the frontpage
def index(request):
	events = Conference.objects.filter(promoactive=True, enddate__gte=datetime.datetime.today()).order_by('startdate')
	series = ConferenceSeries.objects.extra(
		where=["EXISTS (SELECT 1 FROM confreg_conference c WHERE c.series_id=confreg_conferenceseries.id AND c.promoactive)"]
	)

	news = News.objects.filter(datetime__lte=datetime.datetime.today())[:5]
	return render(request, 'index.html', {
		'events': events,
		'series': series,
		'news': news,
	})

# Handle the events frontpage
def eventsindex(request):
	events = list(Conference.objects.filter(promoactive=True, enddate__gte=datetime.datetime.today()).order_by('startdate'))
	past = Conference.objects.filter(promoactive=True, enddate__lt=datetime.datetime.today()).order_by('-startdate')[:5]
	series = ConferenceSeries.objects.extra(
		where=["EXISTS (SELECT 1 FROM confreg_conference c WHERE c.series_id=confreg_conferenceseries.id AND c.promoactive)"]
	)

	return render(request, 'events/index.html', {
		'events': events,
		'past': past,
		'series': series,
		'regopen': [e for e in events if e.active],
		'cfpopen': [e for e in events if e.callforpapersopen],
		'cfsopen': [e for e in events if e.callforsponsorsopen],
	})

# Handle past events list
def pastevents(request):
	events = list(Conference.objects.filter(promoactive=True, enddate__gte=datetime.datetime.today()).order_by('startdate'))
	past = Conference.objects.filter(promoactive=True, enddate__lt=datetime.datetime.today()).order_by('-startdate')
	series = ConferenceSeries.objects.extra(
		where=["EXISTS (SELECT 1 FROM confreg_conference c WHERE c.series_id=confreg_conferenceseries.id AND c.promoactive)"]
	)

	return render(request, 'events/past.html', {
		'events': events,
		'past': past,
		'series': series,
	})

# Handle event series listing
def eventseries(request, id):
	series = get_object_or_404(ConferenceSeries, pk=id)
	events = list(series.conference_set.filter(promoactive=True).order_by('startdate'))

	return render(request, 'events/series.html', {
		'series': series,
		'upcoming': [e for e in events if e.enddate >= datetime.datetime.today().date()],
		'past': [e for e in events if e.enddate < datetime.datetime.today().date()],
	})

# Handle CSRF failures
def csrf_failure(request, reason=''):
	resp = render(request, 'csrf_failure.html', {
		'reason': reason,
		})
	resp.status_code = 403 # Forbidden
	return resp
