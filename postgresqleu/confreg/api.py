from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

from datetime import datetime, timedelta, time
from urllib.parse import urlparse, parse_qsl, urlencode
import json
import jwt

from postgresqleu.util.crypto import rsa_get_jwk_struct
from postgresqleu.util.random import generate_random_token
from postgresqleu.util.decorators import global_login_exempt
from .util import get_conference_or_404, activate_conference_timezone, reglog
from .models import ConferenceRegistration, ConferenceRegistrationTemporaryToken


@global_login_exempt
def jwk_json(request, confname):
    conference = get_conference_or_404(confname)
    if not conference.key_public:
        raise Http404()

    r = HttpResponse(json.dumps(
        {
            'keys': [
                rsa_get_jwk_struct(conference.key_public, '{}01'.format(conference.urlname)),
            ]
        }
    ), content_type='application/json')

    # Everybody is allowed to get the JWKs
    r['Access-Control-Allow-Origin'] = '*'
    return r


@login_required
def conference_temp_token(request, confname):
    redir = request.GET.get('redir', None)
    if not redir:
        return HttpResponse("Mandatory parameter missing", status=404)

    redir = urlparse(redir)

    # Create, or replace, a temporary token for this login, which can later be exchanged for a full JWT.
    conference = get_conference_or_404(confname)
    if not conference.key_public:
        return HttpResponse("Conference key not found", status=404)

    # Explicitly compare scheme/location/path, but *not* the querystring.
    if redir._replace(query=None, fragment=None).geturl() not in conference.web_origins.split(','):
        return HttpResponse("Forbidden redirect URL", status=403)

    try:
        reg = ConferenceRegistration.objects.get(conference=conference, attendee=request.user)
    except ConferenceRegistration.DoesNotExist:
        return HttpResponse("You are not registered for this conference", status=403, content_type='text/plain')

    if not reg.payconfirmedat:
        return HttpResponse("Not confirmed for this conference", status=403, conten_type='text/plain')

    with transaction.atomic():
        # If there is an existing token for this user, just remove it.
        ConferenceRegistrationTemporaryToken.objects.filter(reg=reg).delete()

        # Create a new one
        t = ConferenceRegistrationTemporaryToken(
            reg=reg,
            token=generate_random_token(),
            expires=timezone.now() + timedelta(minutes=5),
        )
        t.save()

        reglog(reg, 'Issued temporary token', request.user)

        # If there are any parameters included in the redirect, we just append ours to it
        param = dict(parse_qsl(redir.query))
        param['token'] = t.token

        return HttpResponseRedirect(redir._replace(query=urlencode(param)).geturl())


class CorsResponse(HttpResponse):
    def __init__(self, *args, **kwargs):
        origin = kwargs.pop('origin')
        allowed = kwargs.pop('allowed')
        super().__init__(*args, **kwargs)

        if origin:
            if allowed:
                # Origin is specified, so validate it against it
                for o in allowed.split(','):
                    if o == origin:
                        matched_origin = o
                        break
                else:
                    return self._set_403("Origin not authorized")
            else:
                # If no origin is configured, we're going to use our own sitebase only
                if origin != settings.SITEBASE:
                    return self._set_403("No authorized origins configured")
                matched_origin = settings.SITEBASE
        else:
            matched_origin = settings.SITEBASE

        self['Access-Control-Allow-Origin'] = matched_origin

    def _set_403(self, msg):
        self.content = msg
        self.status = 403


@transaction.atomic
@csrf_exempt
@global_login_exempt
@require_http_methods(["POST"])
def conference_jwt(request, confname):
    temptoken = get_object_or_404(ConferenceRegistrationTemporaryToken, token=request.POST.get('token', None))
    reg = temptoken.reg
    activate_conference_timezone(reg.conference)

    if temptoken.expires < timezone.now():
        # Remove the old token as well
        temptoken.delete()

        return CorsResponse("Token expired", status=403, origin=request.headers.get('Origin', ''), allowed=reg.conference.web_origins)

    # Token was valid -- so the first thing we do is remove it
    temptoken.delete()

    reglog(reg, 'Converted temporary to permanent token')

    # We allow caching of the token until a full day after the conference. This may not be the
    # smartest ever, but it'll do for now and reduce the reliance on this endpoint being
    # available during an event.
    expire = datetime.combine(reg.conference.enddate, time(23, 59)) + timedelta(days=1)

    # Else we're good to go to generate the JWT
    r = CorsResponse(jwt.encode(
        {
            'iat': datetime.utcnow(),
            'exp': expire,
            'iss': settings.SITEBASE,
            'attendee': {
                'name': reg.fullname,
                'email': reg.email,
                'company': reg.company,
                'nick': reg.nick,
                'twittername': reg.twittername,
                'shareemail': reg.shareemail,
                'regid': reg.id,
                'country': reg.countryname,
                'volunteer': reg.is_volunteer,
                'admin': reg.is_admin,
            }
        },
        reg.conference.key_private,
        algorithm='RS256',
        headers={
            'kid': '{}01'.format(reg.conference.urlname),
        },
    ), content_type='application/jwt', origin=request.headers.get('Origin', ''), allowed=reg.conference.web_origins)

    return r
