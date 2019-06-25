from django.conf.urls import url
from django.views.generic import RedirectView

from django.conf import settings

import postgresqleu.oauthlogin.views
import postgresqleu.oauthlogin.oauthclient

postgresqleu.oauthlogin.oauthclient.configure()


oauthurlpatterns = [
    url(r'^accounts/login/?$', postgresqleu.oauthlogin.views.login),
    url(r'^accounts/logout/?$', postgresqleu.oauthlogin.views.logout),
    url(r'^login/$', RedirectView.as_view(url='/accounts/login/')),
    url(r'^logout/$', RedirectView.as_view(url='/accounts/logout/')),
]


for provider in list(settings.OAUTH.keys()):
    oauthurlpatterns.append(url(r'^accounts/login/({0})/$'.format(provider), postgresqleu.oauthlogin.oauthclient.login_oauth))
