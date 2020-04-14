from django import http
from django import shortcuts
from django.utils import timezone
from django.conf import settings

import base64


class GlobalLoginMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, callback, callback_args, callback_kwargs):
        if not settings.GLOBAL_LOGIN_USER or not settings.GLOBAL_LOGIN_PASSWORD:
            # Not configured to do global auth
            return None

        if getattr(callback, 'global_login_exempt', False):
            # No global auth on this specific url
            return None

        if 'HTTP_AUTHORIZATION' in request.META:
            auth = request.META['HTTP_AUTHORIZATION'].split()
            if len(auth) != 2:
                return http.HttpResponseForbidden("Invalid authentication")
            if auth[0].lower() == "basic":
                user, pwd = base64.b64decode(auth[1]).decode('utf8').split(':')
                if user == settings.GLOBAL_LOGIN_USER and pwd == settings.GLOBAL_LOGIN_PASSWORD:
                    return None
            # Else we fall through and request a login prompt

        response = http.HttpResponse()
        response.status_code = 401
        response['WWW-Authenticate'] = 'Basic realm={0}'.format(settings.SITEBASE)
        return response


# Ability to redirect using raise()
class RedirectException(Exception):
    def __init__(self, url):
        self.url = url


class RedirectMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if isinstance(exception, RedirectException):
            return shortcuts.redirect(exception.url)


# Enforce that we deactivate the timezone before each request to make the
# thread return back to the default timezone, since django does *not*
# reset this on a per-thread basis.
class TzMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        timezone.deactivate()
        return self.get_response(request)
