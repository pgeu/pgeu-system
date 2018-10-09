#
# Script to post previosly unposted news to twitter
#
#

from django.core.management.base import BaseCommand, CommandError
from django.template.defaultfilters import slugify
from django.db import connection
from django.conf import settings

from datetime import datetime, timedelta
import time

from postgresqleu.newsevents.models import News
from postgresqleu.confreg.models import ConferenceNews

import requests_oauthlib


def make_twitter_post(tw, statusstr):
	# Don't post more often than once / 10 seconds, to not trigger flooding.
	time.sleep(10)

	r = tw.post('https://api.twitter.com/1.1/statuses/update.json', data={
		'status': statusstr,
	})
	if r.status_code != 200:
		print("Failed to post to twitter: %s " % r)
		return False
	return True

class Command(BaseCommand):
	help = 'Post to twitter'

	def handle(self, *args, **options):
		curs = connection.cursor()
		curs.execute("SELECT pg_try_advisory_lock(981273)")
		if not curs.fetchall()[0][0]:
			raise CommandError("Failed to get advisory lock, existing twitter_post process stuck?")

		if settings.TWITTER_NEWS_TOKEN:
			articles = list(News.objects.filter(tweeted=False, datetime__gt=datetime.now()-timedelta(days=7), datetime__lt=datetime.now()).order_by('datetime'))
		else:
			articles = []

		if articles:
			tw = requests_oauthlib.OAuth1Session(settings.TWITTER_CLIENT,
												 settings.TWITTER_CLIENTSECRET,
												 settings.TWITTER_NEWS_TOKEN,
												 settings.TWITTER_NEWS_TOKENSECRET)

			for a in articles:
				# We hardcode 30 chars for the URL shortener. And then 10 to cover the intro and spacing.
				statusstr = u"{0} {1}/news/{2}-{3}/".format(a.title[:140-40],
															settings.SITEBASE,
															slugify(a.title),
															a.id)
				if make_twitter_post(tw, statusstr):
					a.tweeted = True
					a.save()

		articles = list(ConferenceNews.objects.select_related('conference').filter(tweeted=False, datetime__gt=datetime.now()-timedelta(days=7), datetime__lt=datetime.now(), conference__twittersync_active=True).order_by('conference__id', 'datetime'))
		lastconference = None
		for a in articles:
			if a.conference != lastconference:
				lastconference = a.conference
				tw = requests_oauthlib.OAuth1Session(settings.TWITTER_CLIENT,
													 settings.TWITTER_CLIENTSECRET,
													 a.conference.twitter_token,
													 a.conference.twitter_secret)

			statusstr = u"{0} {1}##{2}".format(a.title[:140-40],
											   lastconference.confurl,
											   a.id)
			if make_twitter_post(tw, statusstr):
				a.tweeted = True
				a.save()
