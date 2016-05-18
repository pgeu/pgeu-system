# Index has a very special view that lives out here
from django.shortcuts import render_to_response

from postgresqleu.newsevents.models import News, Event

import datetime

# Handle the frontpage
def index(request):
	events = Event.objects.filter(startdate__gte=datetime.datetime.today())[:3]
	news = News.objects.filter()[:5]
	return render_to_response('index.html', {
		'events': events,
		'news': news,
	})

# Handle CSRF failures
def csrf_failure(request, reason=''):
	resp = render_to_response('csrf_failure.html', {
		'reason': reason,
		})
	resp.status_code = 403 # Forbidden
	return resp
