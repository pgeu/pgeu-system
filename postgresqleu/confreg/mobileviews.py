from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, Http404
from django.db import connection
from django.conf import settings

import markdown
import urllib2
from urllib import urlencode

from models import Conference

from datetime import datetime

import itertools
import json

# Version of the HTML manifest. This needs to be bumped whenever the
# mobile HTML or Javascript code is changed, to make sure that clients
# properly refresh.
# When running in debug mode, turn off the appcache because it can be
# a real PITA to debug.
if settings.DEBUG:
	MANIFESTVERSION=None
else:
	MANIFESTVERSION=105

def index(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	return render(request, 'confreg/mobile/index.html', {
			'conf': conference,
			'html5manifestversion': MANIFESTVERSION,
			})

def cachemanifest(request, confname):
	# We'll just serve this up whenever, no need to check that the
	# conference exists. We'll break later :)
	return HttpResponse("""CACHE MANIFEST
# revision:%s
/media/jq/jquery.mobile-1.2.0.min.css
/media/jq/jquery-1.8.2.min.js
/media/jq/jquery.mobile-1.2.0.min.js
/media/jq/images/ajax-loader.png
/media/jq/images/ajax-loader.gif
/media/jq/images/icons-18-white.png
/media/jq/images/icons-18-black.png
/media/jq/images/icons-36-white.png
/media/jq/images/icons-36-black.png
NETWORK:
*
""" % (MANIFESTVERSION,),
						content_type='text/cache-manifest')


def conferencedata(request, confname, since):
	conference = get_object_or_404(Conference, urlname=confname)

	if since:
		datefilter = datetime.fromtimestamp(int(since) / 1000)
	else:
		# Yes this is ugly, but i'm too lazy to rewrite the query
		datefilter = datetime.fromtimestamp(0)

	# Yeah, the django ORM is uncapable of doing this in a smart way...
	curs = connection.cursor()
	curs.execute("SELECT s.id, s.title, s.abstract, s.starttime, s.endtime, r.roomname, array_agg(csp.speaker_id) AS speakers FROM confreg_conferencesession s INNER JOIN confreg_conferencesession_speaker csp ON csp.conferencesession_id=s.id LEFT JOIN confreg_room r ON r.id=s.room_id WHERE s.conference_id=%(confid)s AND status=1 AND NOT starttime IS NULL AND lastmodified > %(lastmod)s GROUP BY s.id, s.title, s.abstract, s.starttime, s.endtime, r.roomname ORDER BY s.starttime", {
			'confid': conference.id,
			'lastmod': datefilter,
			})

	sessiondata = [{'i': r[0], 't': r[1], 'a': markdown.markdown(r[2], safe_mode=True), 'st': r[3].isoformat() + 'Z', 'et': r[4].isoformat() + 'Z', 'r': r[5] and r[5] or '', 's': r[6]} for r in curs.fetchall()]
#	sessions = ConferenceSession.objects.select_related('speaker').filter(conference=conference, starttime__isnull=False).order_by('starttime')


	# Now get all speaker info
	curs.execute("SELECT spk.id, spk.fullname, spk.abstract FROM confreg_speaker spk WHERE EXISTS (SELECT 1 FROM confreg_conferencesession_speaker csp INNER JOIN confreg_conferencesession s ON s.id=csp.conferencesession_id WHERE s.conference_id=%(confid)s AND status=1 AND NOT starttime IS NULL AND csp.speaker_id=spk.id) AND spk.lastmodified > %(lastmod)s", {
			'confid': conference.id,
			'lastmod': datefilter,
			})

	speakerdata = [{'i': r[0], 'n': r[1], 'a': markdown.markdown(r[2], safe_mode=True)} for r in curs.fetchall()]

	# Get all deleted items
	if since:
		curs.execute("SELECT itemid, type FROM confreg_deleteditems WHERE deltime>%(lastmod)s ORDER BY type", {
				'lastmod': datefilter,
				})
		deldata = dict([(k, [i for i,t in v]) for k,v in itertools.groupby(curs.fetchall(), lambda t: t[1])])
	else:
		deldata = {}

	resp = HttpResponse(content_type='application/json')
	json.dump({
		'c': {
			'news': conference.newsjson,
		},
		's': sessiondata,
		'sp': speakerdata,
		'd': deldata,
		'status': 'OK',
		}, resp)
	return resp

def newsproxy(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.newsjson:
		raise Http404("Invalid conference")

	for k in request.GET.keys():
		if k not in ('since', 'callback', '_'):
			raise Exception("Invalid parameter")

	# Proxy request
	try:
		u = urllib2.urlopen("%s?%s" % (conference.newsjson, urlencode(request.GET)))
		r = u.read()
		u.close()
	except:
		raise Http404("News load failure")

	return HttpResponse(r, content_type='application/json')
