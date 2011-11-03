from django.conf.urls.defaults import *
from django.conf import settings
from django.contrib.auth.views import login, logout_then_login
from django.contrib import admin
from django.views.generic.simple import redirect_to

import postgresqleu.static.views
import postgresqleu.newsevents.views
import postgresqleu.views
import postgresqleu.confreg.views
import postgresqleu.membership.views
import postgresqleu.elections.views
import postgresqleu.invoicemgr.views

from postgresqleu.newsevents.feeds import LatestNews, LatestEvents

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
admin.autodiscover()


# Feeds
feeds = {
	'news': LatestNews,
	'events': LatestEvents,
}

urlpatterns = patterns('',
	# Frontpage
	(r'^$', postgresqleu.views.index),

	# Log in/log out
	(r'^login/?$', login, {'template_name':'login.html'}),
	(r'^logout/?$', logout_then_login, {'login_url':'/'}),
	(r'^accounts/login/$', login, {'template_name':'login.html'}),
	(r'^accounts/logout/$', logout_then_login, {'login_url':'/'}),

	# News & Events
	(r'^events$', postgresqleu.newsevents.views.eventlist),
	(r'^events/(\d+)$', postgresqleu.newsevents.views.event),
	(r'^events/archive$', postgresqleu.newsevents.views.eventarchive),

	# Feeds
	(r'^feeds/(?P<url>.*)/$', 'django.contrib.syndication.views.feed', {'feed_dict': feeds}),

	# Conference registration
	(r'^events/register/([^/]+)/$', postgresqleu.confreg.views.home),
	(r'^events/feedback/([^/]+)/$', postgresqleu.confreg.views.feedback),
	(r'^events/feedback/([^/]+)/(\d+)/$', postgresqleu.confreg.views.feedback_session),
	(r'^events/feedback/([^/]+)/conference/$', postgresqleu.confreg.views.feedback_conference),
	(r'^events/feedback/$', postgresqleu.confreg.views.feedback_available),
	(r'^events/schedule/([^/]+)/$', postgresqleu.confreg.views.schedule),
	(r'^events/schedule/([^/]+)/ical/$', postgresqleu.confreg.views.schedule_ical),
	(r'^events/schedule/([^/]+)/session/(\d+)(-.*)?/$', postgresqleu.confreg.views.session),
	(r'^events/sessions/([^/]+)/session/(\d+)(-.*)?/$', postgresqleu.confreg.views.session),
	(r'^events/schedule/([^/]+)/speaker/(\d+)(-.*)?/$', postgresqleu.confreg.views.speaker),
	(r'^events/sessions/([^/]+)/speaker/(\d+)(-.*)?/$', postgresqleu.confreg.views.speaker),
	(r'^events/schedule/([^/]+)/create/$', postgresqleu.confreg.views.createschedule),
	(r'^events/schedule/([^/]+)/create/publish/$', postgresqleu.confreg.views.publishschedule),
	(r'^events/sessions/([^/]+)/$', postgresqleu.confreg.views.sessionlist),
	(r'^events/speaker/(\d+)/photo/$', postgresqleu.confreg.views.speakerphoto),
	(r'^events/speakerprofile/$', postgresqleu.confreg.views.speakerprofile),
	(r'^events/speakerprofile/(\w+)/$', postgresqleu.confreg.views.speakerprofile),
	(r'^events/callforpapers/(\w+)/$', postgresqleu.confreg.views.callforpapers),
	(r'^events/callforpapers/(\w+)/new/$', postgresqleu.confreg.views.callforpapers_new),
	(r'^events/callforpapers/(\w+)/(\d+)/$', postgresqleu.confreg.views.callforpapers_edit),
	(r'^events/register/(\w+)/prepaid/(\d+)/$', postgresqleu.confreg.views.prepaid),
	(r'^events/prepaid/$', postgresqleu.confreg.views.createvouchers),
	(r'^events/prepaid/(\d+)/$', postgresqleu.confreg.views.viewvouchers),
    (r'^events/reports/(\w+)/$', postgresqleu.confreg.views.reports),

	# Membership management
	(r'^membership/$', postgresqleu.membership.views.home),
	(r'^community/members/$', postgresqleu.membership.views.userlist),

	# Merchandise redirect
	(r'^merchandise/', redirect_to, {'url': 'http://postgresqleu.spreadshirt.net/'}),

	# Elections
	(r'^elections/$', postgresqleu.elections.views.home),
	(r'^elections/(\d+)/$', postgresqleu.elections.views.election),
	(r'^elections/(\d+)/candidate/(\d+)/$', postgresqleu.elections.views.candidate),
	(r'^elections/(\d+)/ownvotes/$', postgresqleu.elections.views.ownvotes),

	# Invoice manager (admins only!)
	(r'invoicemgr/$', postgresqleu.invoicemgr.views.home),
	(r'invoicemgr/(\d+)/$', postgresqleu.invoicemgr.views.invoice),
	(r'invoicemgr/(\d+)/pdf/$', postgresqleu.invoicemgr.views.invoicepdf),
	(r'invoicemgr/new/$', postgresqleu.invoicemgr.views.create),
	(r'invoicemgr/new/conf/(\d+/)?$', postgresqleu.invoicemgr.views.conf),

	# This should not happen in production - serve by apache!
	url(r'^media/(.*)$', 'django.views.static.serve', {
		'document_root': '../media',
	}),
	url(r'^(favicon.ico)$', 'django.views.static.serve', {
		'document_root': '../media',
	}),

	# Admin site
	(r'^admin/(.*)$', admin.site.root),

	# Fallback - send everything nonspecific to the static handler
	(r'^(.*)/$', postgresqleu.static.views.static_fallback),
)
