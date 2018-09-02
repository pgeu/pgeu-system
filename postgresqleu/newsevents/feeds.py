from django.contrib.syndication.views import Feed
from django.conf import settings

from models import News

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

