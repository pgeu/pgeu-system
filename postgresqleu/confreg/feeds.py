from django.contrib.syndication.views import Feed
from django.conf import settings

from models import Conference

import datetime

class LatestEvents(Feed):
	title = "Events - %s" % settings.ORG_NAME
	link = "/"
	description = "Upcoming events from %s" % settings.ORG_NAME
	description_template = "events/rssevent.html"

	def items(self):
		return Conference.objects.filter(promoactive=True, enddate__gte=datetime.datetime.now())

	def item_link(self, conference):
		return "%s/events/%s/" % (settings.SITEBASE, conference.urlname)

