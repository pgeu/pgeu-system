from django.conf.urls.defaults import *
from django.conf import settings
from django.contrib.auth.views import login, logout_then_login


import postgresqleu.static.views

# Uncomment the next two lines to enable the admin:
# from django.contrib import admin
# admin.autodiscover()

urlpatterns = patterns('',
	# Frontpage
	(r'^$', postgresqleu.static.views.index),

	# Log in/log out
	(r'^login/?$', login, {'template_name':'login.html'}),
	(r'^logout/?$', logout_then_login, {'login_url':'/'}),

	# This should not happen in production - serve by apache!
	url(r'^media/(.*)$', 'django.views.static.serve', {
		'document_root': '../media',
	}),

	# Fallback - send everything nonspecific to the static handler
	(r'^(.*)$', postgresqleu.static.views.static_fallback),
)
