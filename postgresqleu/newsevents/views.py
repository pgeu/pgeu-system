from django.shortcuts import render_to_response
from django.http import HttpResponse, Http404
from django.template import TemplateDoesNotExist, loader, Context

from postgresqleu.newsevents.models import *

import datetime

def eventlist(request):
	events = Event.objects.filter(startdate__gte=datetime.datetime.today)
	return render_to_response('pages/events.html', {
		"events": events,
	})
	
def event(request, eventid):
	event = get_object_or_404(Event, id=eventid)
	return render_to_response('pages/singleevent.html', {
		"event": event,
	})
	
def eventarchive(request):
	events = Event.objects.all(startdate__lte=datetime.datetime.today)
	return render_to_response('pages/eventarchive.html', {
		"events": events,
	})

