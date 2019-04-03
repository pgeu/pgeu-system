from django.shortcuts import render, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings

from postgresqleu.util.db import exec_to_list, exec_to_dict
from postgresqleu.util.qr import generate_base64_qr
from postgresqleu.mailqueue.util import send_template_mail

from .models import Conference, ConferenceRegistration
from .views import render_conference_response

import datetime
import json


@login_required
def landing(request, urlname):
    conference = get_object_or_404(Conference, urlname=urlname)
    reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user)

    if not reg.checkinprocessors_set.filter(pk=conference.pk).exists():
        raise PermissionDenied()

    link = "{0}/events/{1}/checkin/{2}/".format(settings.SITEBASE, conference.urlname, reg.regtoken)

    if request.method == 'POST' and request.POST.get('op') == 'sendmail':
        send_template_mail(conference.contactaddr,
                           reg.email,
                           "[{0}] Your check-in link".format(conference.conferencename),
                           "confreg/mail/checkin_link.txt",
                           {
                               'conference': conference,
                               'reg': reg,
                               'link': link,
                           },
                           sendername=conference.conferencename,
                           receivername=reg.fullname)
        messages.info(request, "Link has been sent to {0}".format(reg.email))
        return HttpResponseRedirect(".")

    return render_conference_response(request, conference, 'reg', 'confreg/checkin_landing.html', {
        'reg': reg,
        'checkinlink': link,
        'qrlink': generate_base64_qr(link, 5, 200),
        'qrtest': generate_base64_qr("ID$TESTTESTTESTTEST$ID", 2, 150),
    })


def _get_checkin(request, urlname, regtoken):
    conference = get_object_or_404(Conference, urlname=urlname)
    reg = get_object_or_404(ConferenceRegistration,
                            conference=conference,
                            regtoken=regtoken,
    )

    if not reg.checkinprocessors_set.filter(pk=conference.pk).exists():
        raise PermissionDenied()

    is_admin = conference.administrators.filter(pk=reg.attendee_id).exists()

    return (conference, reg, is_admin)


def checkin(request, urlname, regtoken):
    (conference, reg, is_admin) = _get_checkin(request, urlname, regtoken)

    # By default render the base page
    return render(request, 'confreg/checkin.html', {
        'conference': conference,
        'is_admin': is_admin,
    })


def _json_response(d):
    return HttpResponse(json.dumps(d, cls=DjangoJSONEncoder), content_type='application/json')


def _get_statistics(conference):
    return [
        (
            ('Registration types', 'Done', 'Left'),
            exec_to_list("SELECT regtype, count(1) FILTER (WHERE checkedinat IS NOT NULL), count(1) FILTER (WHERE checkedinat IS NULL) FROM confreg_conferenceregistration r INNER JOIN confreg_registrationtype rt ON rt.id=r.regtype_id WHERE r.conference_id=%(confid)s AND payconfirmedat IS NOT NULL GROUP BY ROLLUP(1) ORDER BY 1", {'confid': conference.id})
        ),
        (
            ('Check in users', 'Done', ''),
            exec_to_list("SELECT username, count(1), NULL FROM confreg_conferenceregistration r INNER JOIN confreg_conferenceregistration r2 ON r2.id=r.checkedinby_id INNER JOIN auth_user u ON u.id=r2.attendee_id WHERE r.conference_id=%(confid)s AND r.payconfirmedat IS NOT NULL AND r.checkedinat IS NOT NULL GROUP BY 1 ORDER BY 2 DESC", {'confid': conference.id})
        ),
        (
            ('Latest checkins', 'By', 'Who'),
            exec_to_list("SELECT to_char(r.checkedinat, 'ddth hh24:mi:ss'), username, r.firstname || ' ' || r.lastname FROM confreg_conferenceregistration r INNER JOIN confreg_conferenceregistration r2 ON r2.id=r.checkedinby_id INNER JOIN auth_user u ON u.id=r2.attendee_id WHERE r.conference_id=%(confid)s AND r.payconfirmedat IS NOT NULL AND r.checkedinat IS NOT NULL ORDER BY r.checkedinat DESC LIMIT 10", {"confid": conference.id})
        ),
    ]


def _get_reg_json(r):
    d = {
        'id': r.id,
        'name': r.fullname,
        'type': r.regtype.regtype,
        'company': r.company,
        'tshirt': r.shirtsize and r.shirtsize.shirtsize,
        'additional': [a.name for a in r.additionaloptions.all()]
    }
    if r.conference.askphotoconsent:
        d['photoconsent'] = r.photoconsent and "Photos OK" or "Photos NOT OK"
    if r.checkedinat:
        d['checkedin'] = {
            'at': r.checkedinat,
            'by': r.checkedinby.fullname,
        }
    if r.queuepartition:
        d['partition'] = r.queuepartition
    return d


@csrf_exempt
def api(request, urlname, regtoken, what):
    (conference, user, is_admin) = _get_checkin(request, urlname, regtoken)

    if what == 'status':
        return _json_response({
            'user': user.attendee.username,
            'name': user.fullname,
            'active': conference.checkinactive,
        })

    if not conference.checkinactive:
        return HttpResponse("Check-in not open", status=412)

    if what == 'lookup':
        token = request.GET.get('lookup')
        if not (token.startswith('ID$') and token.endswith('$ID')):
            raise Http404()
        token = token[3:-3]
        r = get_object_or_404(ConferenceRegistration, conference=conference, payconfirmedat__isnull=False, idtoken=token)
        return _json_response({'reg': _get_reg_json(r)})
    elif what == 'search':
        s = request.GET.get('search').strip()
        return _json_response({
            'regs': [_get_reg_json(r) for r in ConferenceRegistration.objects.filter(
                Q(firstname__icontains=s) | Q(lastname__icontains=s),
                conference=conference, payconfirmedat__isnull=False
            )],
        })
    elif is_admin and what == 'stats':
        return _json_response(_get_statistics(conference))
    elif request.method == 'POST' and what == 'checkin':
        if not conference.checkinactive:
            return HttpResponse("Check-in not open", status=412)

        reg = get_object_or_404(ConferenceRegistration, conference=conference, payconfirmedat__isnull=False, pk=request.POST.get('reg'))
        if reg.checkedinat:
            return HttpResponse("Already checked in.", status=412)
        reg.checkedinat = datetime.datetime.now()
        reg.checkedinby = user
        reg.save()
        return _json_response({
            'reg': _get_reg_json(reg),
        })
    else:
        raise Http404()
