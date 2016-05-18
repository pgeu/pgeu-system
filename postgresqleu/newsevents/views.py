from django.shortcuts import render_to_response, get_object_or_404

from postgresqleu.newsevents.models import Event

import datetime

def eventlist(request):
	events = Event.objects.filter(startdate__gte=datetime.datetime.today())
	return render_to_response('pages/events.html', {
		"events": events,
	})
	
def event(request, eventid):
	event = get_object_or_404(Event, id=eventid)
	return render_to_response('pages/singleevent.html', {
		"obj": event,
	})
	
def eventarchive(request):
	events = Event.objects.filter(startdate__lte=datetime.datetime.today())
	return render_to_response('pages/eventarchive.html', {
		"events": events,
	})

