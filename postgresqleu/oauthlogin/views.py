from django.shortcuts import render
import django.contrib.auth.views as authviews
from django.conf import settings


def login(request):
    return render(request, 'oauthlogin/login.html', {
        'oauth_providers': [(k, v) for k, v in sorted(settings.OAUTH.items())],
    })


def logout(request):
    return authviews.logout_then_login(request, login_url='/')
