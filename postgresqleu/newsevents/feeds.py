from django.contrib.syndication.views import Feed
from django.conf import settings

from models import News, Event

import datetime

class LatestNews(Feed):
	title = "News - %s" % settings.ORG_NAME
	link = "/"
	description = "The latest news from %s" % settings.ORG_NAME
	description_template = "pieces/news_description.html"
	
	def items(self):
		return News.objects.all()[:10]
		
	def item_link(self, news):
		return "%s/news/%s" % (settings.SITEBASE, news.id)

class LatestEvents(Feed):
	title = "Events - %s" % settings.ORG_NAME
	link = "%s/events/" % settings.SITEBASE
	description = "The latest events from %s" % settings.ORG_NAME
	description_template = "pieces/event_description.html"
	
	def items(self):
		return Event.objects.filter(startdate__gte=datetime.datetime.today())[:10]
		
	def item_link(self, event):
		return "%s/events/%s" % (settings.SITEBASE, event.id)

	def item_pubdate(self, event):
		# RSS feed needs a datetime object, not a date object
		return datetime.datetime.fromordinal(event.startdate.toordinal())

