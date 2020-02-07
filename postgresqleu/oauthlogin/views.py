from django.shortcuts import render
import django.contrib.auth.views as authviews
from django.conf import settings

from urllib.parse import quote


def login(request):
    return render(request, 'oauthlogin/login.html', {
        'oauth_providers': [(k, v) for k, v in sorted(settings.OAUTH.items())],
        'next': quote(request.GET.get('next', '')),
    })


def logout(request):
    return authviews.logout_then_login(request, login_url='/')
