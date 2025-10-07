from django.shortcuts import render, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.db.models import Q
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.conf import settings

from collections import OrderedDict
import re

from postgresqleu.util.db import exec_to_list
from postgresqleu.util.db import ensure_conference_timezone
from postgresqleu.util.qr import generate_base64_qr
from postgresqleu.util.decorators import global_login_exempt
from postgresqleu.util.request import get_int_or_error
from postgresqleu.util.time import datetime_string
from postgresqleu.confsponsor.scanning import SponsorScannerHandler, SponsorScanner

from .models import ConferenceRegistration
from .util import render_conference_response, reglog
from .util import send_conference_mail, get_conference_or_404

import json


@login_required
def landing(request, urlname):
    conference = get_conference_or_404(urlname)
    reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user)

    if not reg.checkinprocessors_set.filter(pk=conference.pk).exists():
        raise PermissionDenied()

    link = "{0}/events/{1}/checkin/{2}/".format(settings.SITEBASE, conference.urlname, reg.regtoken)

    links = [
        ('Check-in' if conference.scannerfields else None, link, generate_base64_qr(link, 5, 100)),
    ]
    for f in conference.scannerfields.split(','):
        if not f:  # Splitting the empty string yields an empty entry
            continue
        fieldlink = '{}f{}/'.format(link, f,)
        links.append(
            (f.title(), fieldlink, generate_base64_qr(fieldlink, 5, 100)),
        )

    return render_conference_response(request, conference, 'reg', 'confreg/checkin_landing.html', {
        'reg': reg,
        'links': links,
        'qrtest': generate_base64_qr('{}/t/id/TESTTESTTESTTEST/'.format(settings.SITEBASE), 2, 150),
    })


def _get_checkin(request, urlname, regtoken):
    conference = get_conference_or_404(urlname)
    reg = get_object_or_404(ConferenceRegistration,
                            conference=conference,
                            regtoken=regtoken,
    )

    if not reg.checkinprocessors_set.filter(pk=conference.pk).exists():
        raise PermissionDenied()

    is_admin = conference.administrators.filter(pk=reg.attendee_id).exists()

    return (conference, reg, is_admin)


def _do_checkin_scan(request, conference, is_admin, extra=None):
    c = {
        'conference': conference,
        'is_admin': is_admin,
        'title': 'attendee checkin',
        'doing': 'Check-in attendee',
        'scanwhat': 'ticket',
        'searchwhat': 'registration',
        'has_status': True,
        'has_stats': True,
        'scannertype': 'User',
        'storebutton': 'Check in',
        'expectedtype': 'id',
        'scanfields': [
            ["name", "Name"],
            ["type", "Registration type"],
            ["checkinmessage", "Check-in message"],
            ["policyconfirmed", "Policy confirmed"],
            ["photoconsent", "Photo consent"],
            ["tshirt", "T-Shirt size"],
            ["company", "Company"],
            ["partition", "Queue Partition"],
            ["additional", "Additional options"],
        ],
        'tokentype': 'id',
    }
    if extra:
        c.update(extra)

    return render(request, 'confreg/scanner_app.html', c)


def checkin(request, urlname, regtoken):
    (conference, reg, is_admin) = _get_checkin(request, urlname, regtoken)

    return _do_checkin_scan(request, conference, is_admin, None)


def checkin_field(request, urlname, regtoken, fieldname):
    (conference, reg, is_admin) = _get_checkin(request, urlname, regtoken)

    if fieldname not in conference.scannerfields_list:
        raise Http404()

    return CheckinFieldScannerHandler(reg, None, fieldname).launch(request)


@login_required
def checkin_token(request, scanned_token):
    if scanned_token == 'TESTTESTTESTTEST':
        return HttpResponse("You have successfully scanned the test token.")

    # Tricky to not leak data, but we try.
    foundreg = get_object_or_404(ConferenceRegistration, idtoken=scanned_token)
    conference = foundreg.conference
    reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user)
    is_admin = conference.administrators.filter(pk=reg.attendee_id).exists()

    if not reg.checkinprocessors_set.filter(pk=conference.pk).exists():
        raise PermissionDenied()

    return _do_checkin_scan(request, conference, is_admin, {
        'singletoken': scanned_token,
        'basehref': '{}/events/{}/checkin/{}/'.format(settings.SITEBASE, conference.urlname, reg.regtoken),
    })


class CheckinFieldScannerHandler:
    def __init__(self, reg, foundreg, fieldname):
        self.reg = reg
        self.foundreg = foundreg
        self.fieldname = fieldname

    def launch(self, request, scanned_token=None):
        return render(request, 'confreg/scanner_app.html', {
            'conference': self.reg.conference,
            'title': '{} scan'.format(self.fieldname),
            'doing': 'Scan badge for {}'.format(self.fieldname),
            'scanwhat': 'badge',
            'scannertype': self.fieldname.title(),
            'storebutton': 'Store date for {}'.format(self.fieldname),
            'expectedtype': 'at',
            'scanfields': [
                ["name", "Name"],
                ["type", "Registration type"],
                ["tshirt", "T-Shirt size"],
                ["additional", "Additional options"],
            ],
            'tokentype': 'at',
            'singletoken': scanned_token,
            'basehref': '{}/events/{}/checkin/{}/f{}/'.format(
                settings.SITEBASE,
                self.reg.conference.urlname,
                self.reg.regtoken,
                self.fieldname
            ),
        })

    @property
    def title(self):
        return "Attendee {} ({})".format(
            self.fieldname.title(),
            self.foundreg.dynaprops.get(self.fieldname, 'Pending') if self.foundreg else 'Unknown',
        )


@login_required
def badge_token(request, scanned_token, what=None):
    if scanned_token == 'TESTTESTTESTTEST':
        return HttpResponse("You have successfully scanned the test token.")

    # This is a public token, so try to find it. We need to find the registration right
    # away so we can figure out if the scanner has permissions, and then we're going to
    # find it again later with an API lookup.
    foundreg = get_object_or_404(ConferenceRegistration, publictoken=scanned_token)
    conference = foundreg.conference
    reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user)

    # The user scanning may *either* be a sponsor scanner *or* we have some conference
    # specific fields that checkin-scanners work on.
    sponsorscanners = list(SponsorScanner.objects.filter(sponsor__conference=conference, scanner=reg))

    options = OrderedDict()
    if conference.scannerfields and reg.checkinprocessors_set.filter(pk=conference.pk).exists():
        for f in conference.scannerfields.split(','):
            if f != '':
                options['f{}'.format(f)] = CheckinFieldScannerHandler(reg, foundreg, f)

    for s in sponsorscanners:
        options['s{}'.format(s.id)] = SponsorScannerHandler(s)

    if len(options) == 0:
        raise Http404()
    elif len(options) == 1:
        # Just a single option available, so launch this one
        for k, v in options.items():
            return v.launch(request, scanned_token)
    else:
        # Has a choice already been made?
        if what:
            w = what.rstrip('/')
            if w not in options:
                raise Http404()
            return options[w].launch(request, scanned_token)

        # Else we give them a choice of what to scan
        return render(request, 'confreg/scanchoice.html', {
            'conference': conference,
            'options': options.items(),
        })


def _json_response(d):
    return HttpResponse(json.dumps(d, cls=DjangoJSONEncoder), content_type='application/json')


def _get_statistics(conference):
    return [
        (
            ('Registration types', 'Done', 'Left'),
            exec_to_list("SELECT regtype, count(1) FILTER (WHERE checkedinat IS NOT NULL), count(1) FILTER (WHERE checkedinat IS NULL) FROM confreg_conferenceregistration r INNER JOIN confreg_registrationtype rt ON rt.id=r.regtype_id WHERE r.conference_id=%(confid)s AND payconfirmedat IS NOT NULL AND canceledat IS NULL GROUP BY ROLLUP(1) ORDER BY 1", {'confid': conference.id})
        ),
        (
            ('Check in users', 'Done', ''),
            exec_to_list("SELECT username, count(1), NULL FROM confreg_conferenceregistration r INNER JOIN confreg_conferenceregistration r2 ON r2.id=r.checkedinby_id INNER JOIN auth_user u ON u.id=r2.attendee_id WHERE r.conference_id=%(confid)s AND r.payconfirmedat IS NOT NULL AND r.canceledat IS NULL AND r.checkedinat IS NOT NULL GROUP BY 1 ORDER BY 2 DESC", {'confid': conference.id})
        ),
        (
            ('Latest checkins', 'By', 'Who'),
            exec_to_list("SELECT to_char(r.checkedinat, 'ddth hh24:mi:ss'), username, r.firstname || ' ' || r.lastname FROM confreg_conferenceregistration r INNER JOIN confreg_conferenceregistration r2 ON r2.id=r.checkedinby_id INNER JOIN auth_user u ON u.id=r2.attendee_id WHERE r.conference_id=%(confid)s AND r.payconfirmedat IS NOT NULL AND r.canceledat IS NULL AND r.checkedinat IS NOT NULL ORDER BY r.checkedinat DESC LIMIT 10", {"confid": conference.id})
        ),
    ]


def _get_reg_json(r, fieldscan=False):
    d = {
        'id': r.id,
        'name': r.fullname,
        'type': r.regtype.regtype,
        'company': r.company,
        'tshirt': r.shirtsize and r.shirtsize.shirtsize,
        'additional': [a.name for a in r.additionaloptions.all()],
        'token': r.publictoken if fieldscan else r.idtoken,
        'highlight': [],
    }
    if r.conference.askphotoconsent:
        d['photoconsent'] = r.photoconsent and "Photos OK" or "Photos NOT OK"
    if r.conference.confirmpolicy:
        d['policyconfirmed'] = r.policyconfirmedat and "Policy confirmed" or "Policy NOT confirmed"
        if not r.policyconfirmedat:
            d['highlight'].append('policyconfirmed')
    if r.regtype.checkinmessage or r.checkinmessage:
        d['checkinmessage'] = "\n\n".join(m for m in (r.checkinmessage, r.regtype.checkinmessage) if m)
        d['highlight'].append('checkinmessage')
    if r.checkedinat and not fieldscan:
        d['already'] = {
            'title': 'Attendee already checked in',
            'body': 'Attendee was checked in by {} at {}.'.format(r.checkedinby.fullname, r.checkedinat),
        }
    if fieldscan and r.dynaprops.get(fieldscan, None):
        d['already'] = {
            'title': 'Field {} already marked'.format(fieldscan),
            'body': 'Field {} already marked at {}'.format(fieldscan, r.dynaprops[fieldscan]),
        }
    if r.queuepartition:
        d['partition'] = r.queuepartition
    return d


_tokenmatcher = re.compile('^{}/t/id/([^/]+)/$'.format(settings.SITEBASE))
_publictokenmatcher = re.compile('^{}/t/at/([^/]+)/$'.format(settings.SITEBASE))


@csrf_exempt
@global_login_exempt
def api(request, urlname, regtoken, what):
    (conference, user, is_admin) = _get_checkin(request, urlname, regtoken)

    if what == 'status':
        return _json_response({
            'user': user.attendee.username,
            'name': user.fullname,
            'active': conference.checkinactive,
            'activestatus': 'Check-in active' if conference.checkinactive else 'Check-in is not open',
            'confname': conference.conferencename,
            'admin': is_admin,
        })

    # Only the stats API call is allowed when check-in is not open
    if not conference.checkinactive and what != 'stats':
        return HttpResponse("Check-in not open", status=412)

    if what == 'lookup':
        token = request.GET.get('lookup')
        m = _tokenmatcher.match(token)
        if m:
            # New style token
            token = m.group(1)
        else:
            raise Http404()
        r = get_object_or_404(ConferenceRegistration, conference=conference, payconfirmedat__isnull=False, canceledat__isnull=True, idtoken=token)
        return _json_response({'reg': _get_reg_json(r)})
    elif what == 'search':
        s = request.GET.get('search').strip()
        if not s:
            raise Http404()
        q = Q()
        for n in s.split():
            # For each part of the given string, search both first and last name
            # When two or more name parts are specified, require that they all match,
            # but don't care which one matches which part.
            q = q & (Q(firstname__icontains=n) | Q(lastname__icontains=n))
        return _json_response({
            'regs': [_get_reg_json(r) for r in ConferenceRegistration.objects.filter(
                q,
                conference=conference, payconfirmedat__isnull=False, canceledat__isnull=True,
            )],
        })
    elif is_admin and what == 'stats':
        with ensure_conference_timezone(conference):
            return _json_response(_get_statistics(conference))
    elif request.method == 'POST' and what == 'store':
        if not conference.checkinactive:
            return HttpResponse("Check-in not open", status=412)

        # Accept both full URL version of token and just the key part
        m = _tokenmatcher.match(request.POST['token'])
        if m:
            token = m.group(1)
        else:
            token = request.POST['token']
        reg = get_object_or_404(ConferenceRegistration, conference=conference, payconfirmedat__isnull=False, canceledat__isnull=True, idtoken=token)
        if reg.checkedinat:
            return HttpResponse("Already checked in.", status=412)
        reg.checkedinat = timezone.now()
        reg.checkedinby = user
        reg.save()
        return _json_response({
            'reg': _get_reg_json(reg),
            'message': 'Attendee {} checked in successfully.'.format(reg.fullname),
            'showfields': True,
        })
    else:
        raise Http404()


@csrf_exempt
@global_login_exempt
def checkin_field_api(request, urlname, regtoken, fieldname, what):
    (conference, user, is_admin) = _get_checkin(request, urlname, regtoken)
    if fieldname not in conference.scannerfields_list:
        raise Http404()

    if what == 'status':
        return _json_response({
            'user': user.attendee.username,
            'name': user.fullname,
            'active': conference.checkinactive,
            'activestatus': 'Check-in active' if conference.checkinactive else 'Check-in is not open',
            'confname': conference.conferencename,
            'fieldname': fieldname,
            'admin': is_admin,
        })

    if what == 'lookup':
        token = request.GET.get('lookup')
        m = _publictokenmatcher.match(token)
        if m:
            # New style token
            token = m.group(1)
        else:
            raise Http404()
        r = get_object_or_404(ConferenceRegistration, conference=conference, payconfirmedat__isnull=False, canceledat__isnull=True, publictoken=token)
        return _json_response({'reg': _get_reg_json(r, fieldname)})
    elif request.method == 'POST' and what == 'store':
        if not conference.checkinactive:
            return HttpResponse("Check-in not open", status=412)

        m = _publictokenmatcher.match(request.POST['token'])
        if m:
            token = m.group(1)
        else:
            token = request.POST['token']

        with transaction.atomic():
            reg = get_object_or_404(ConferenceRegistration, conference=conference, payconfirmedat__isnull=False, canceledat__isnull=True, publictoken=token)
            reglog(reg, "Marked scanner field {}".format(fieldname), user.attendee)
            reg.dynaprops[fieldname] = datetime_string(timezone.now())
            reg.save(update_fields=['dynaprops'])
        return _json_response({
            'reg': _get_reg_json(reg, fieldname),
            'message': 'Field {} marked for attendee {}.'.format(fieldname, reg.fullname),
        })
    else:
        raise Http404()
