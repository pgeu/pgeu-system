from django.conf.urls.defaults import *
from django.conf import settings
from django.contrib.auth.views import login, logout_then_login
from django.contrib import admin


import postgresqleu.static.views
import postgresqleu.newsevents.views
import postgresqleu.views
import postgresqleu.confreg.views

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
	(r'^events/schedule/([^/]+)/$', postgresqleu.confreg.views.schedule),
	(r'^events/schedule/([^/]+)/ical/$', postgresqleu.confreg.views.schedule_ical),
	(r'^events/schedule/([^/]+)/session/(\d+)(-.*)?/$', postgresqleu.confreg.views.session),
	(r'^events/schedule/([^/]+)/speaker/(\d+)(-.*)?/$', postgresqleu.confreg.views.speaker),
	(r'^events/speaker/(\d+)/photo/$', postgresqleu.confreg.views.speakerphoto),

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
