from django.urls import re_path
from django.views.generic import RedirectView

from django.conf import settings

import postgresqleu.oauthlogin.views
import postgresqleu.oauthlogin.oauthclient

postgresqleu.oauthlogin.oauthclient.configure()


oauthurlpatterns = [
    re_path(r'^accounts/login/?$', postgresqleu.oauthlogin.views.login),
    re_path(r'^accounts/logout/?$', postgresqleu.oauthlogin.views.logout),
    re_path(r'^login/$', RedirectView.as_view(url='/accounts/login/')),
    re_path(r'^logout/$', RedirectView.as_view(url='/accounts/logout/')),
]


for provider in list(settings.OAUTH.keys()):
    oauthurlpatterns.append(re_path(r'^accounts/login/({0})/$'.format(provider), postgresqleu.oauthlogin.oauthclient.login_oauth))
