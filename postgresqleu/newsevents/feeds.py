from django.contrib.syndication.feeds import Feed
from postgresqleu.newsevents.models import *

import datetime

class LatestNews(Feed):
	title = "News - PostgreSQL Europe"
	link = "/"
	description = "The latest news from PostgreSQL Europe"
	description_template = "pieces/news_description.html"
	
	def items(self):
		return News.objects.all()[:10]
		
	def item_link(self, news):
		return "http://www.postgresql.eu/news/%s" % news.id

class LatestEvents(Feed):
	title = "Events - PostgreSQL Europe"
	link = "http://www.postgresql.eu/events/"
	description = "The latest events from PostgreSQL Europe"
	description_template = "pieces/event_description.html"
	
	def items(self):
		return Event.objects.filter(startdate__gte=datetime.datetime.today)[:10]
		
	def item_link(self, event):
		return "http://www.postgresql.eu/events/#%s" % event.id

	def item_pubdate(self, event):
		# RSS feed needs a datetime object, not a date object
		return datetime.datetime.fromordinal(event.startdate.toordinal())

