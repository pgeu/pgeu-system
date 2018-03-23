# Index has a very special view that lives out here
from django.shortcuts import render

from postgresqleu.newsevents.models import News, Event

import datetime

# Handle the frontpage
def index(request):
	events = Event.objects.filter(startdate__gte=datetime.datetime.today())[:5]
	news = News.objects.filter(datetime__lte=datetime.datetime.today())[:5]
	return render(request, 'index.html', {
		'events': events,
		'news': news,
	})

# Handle the news page
def news(request):
	news = News.objects.filter(datetime__lte=datetime.datetime.today())[:5]
	return render(request, 'news.html', {
		'news': news,
	})

# Handle CSRF failures
def csrf_failure(request, reason=''):
	resp = render(request, 'csrf_failure.html', {
		'reason': reason,
		})
	resp.status_code = 403 # Forbidden
	return resp
