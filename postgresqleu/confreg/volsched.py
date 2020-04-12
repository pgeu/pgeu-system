from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Sum, F, Func
from django.conf.urls import url

from datetime import datetime
import json

from postgresqleu.util.db import exec_to_dict
from postgresqleu.util.request import get_int_or_error

from .models import Conference, ConferenceRegistration
from .models import VolunteerSlot, VolunteerAssignment
from .util import send_conference_mail, get_conference_or_404


def _check_admin(request, conference):
    if request.user.is_superuser:
        return True
    else:
        return conference.administrators.filter(pk=request.user.id).exists() or conference.series.administrators.filter(pk=request.user.id).exists()


def _get_conference_and_reg(request, urlname):
    conference = get_conference_or_404(urlname)
    is_admin = _check_admin(request, conference)
    if is_admin:
        reg = ConferenceRegistration.objects.get(conference=conference, attendee=request.user)
    else:
        try:
            reg = conference.volunteers.get(attendee=request.user)
        except ConferenceRegistration.DoesNotExist:
            raise Http404("Volunteer entry not found")

    return (conference, is_admin, reg)


def send_volunteer_notification(conference, assignment, subject, template):
    if not conference.notifyvolunteerstatus:
        return

    # No filter aggregates in our version of Django, so direct SQL it is
    pending = exec_to_dict("SELECT count(*) FILTER (WHERE NOT org_confirmed) AS admin, count(*) FILTER (WHERE NOT vol_confirmed) AS volunteer FROM  confreg_volunteerassignment a INNER JOIN confreg_volunteerslot s ON s.id=a.slot_id WHERE s.conference_id=%(confid)s", {
        'confid': conference.id,
    })[0]

    send_conference_mail(conference,
                         conference.notifyaddr,
                         subject,
                         'confreg/mail/{}'.format(template), {
                             'conference': conference,
                             'assignment': assignment,
                             'pending': pending,
                         },
                         sender=conference.notifyaddr,
                         receivername=conference.conferencename,
    )


def _get_volunteer_stats(conference):
    stats = ConferenceRegistration.objects.filter(conference=conference) \
                                          .filter(volunteers_set=conference) \
                                          .annotate(num_assignments=Count('volunteerassignment')) \
                                          .annotate(total_time=Sum(Func(
                                              Func(F('volunteerassignment__slot__timerange'), function='upper'),
                                              Func(F('volunteerassignment__slot__timerange'), function='lower'),
                                              function='age'))) \
                                          .order_by('lastname', 'firstname')

    return [{
        'name': r.fullname,
        'count': r.num_assignments,
        'time': str(r.total_time or '0:00:00'),
    } for r in stats]


def _slot_return_data(slot):
    return {
        'id': slot.id,
        'max_staff': slot.max_staff,
        'min_staff': slot.min_staff,
        'assignments': [{
            'id': a.id,
            'volid': a.reg.id,
            'volunteer': a.reg.fullname,
            'vol_confirmed': a.vol_confirmed,
            'org_confirmed': a.org_confirmed,
        } for a in slot.volunteerassignment_set.all()],
    }


@login_required
@transaction.atomic
def volunteerschedule_api(request, urlname, adm=False):
    try:
        (conference, can_admin, reg) = _get_conference_and_reg(request, urlname)
    except ConferenceRegistration.DoesNotExist:
        raise PermissionDenied()

    is_admin = can_admin and adm

    if request.method == 'GET':
        # GET just always returns the complete volunteer schedule
        slots = VolunteerSlot.objects.prefetch_related('volunteerassignment_set', 'volunteerassignment_set__reg').filter(conference=conference)
        return HttpResponse(json.dumps({
            'slots': [_slot_return_data(slot) for slot in slots],
            'volunteers': [{
                'id': vol.id,
                'name': vol.fullname,
            } for vol in conference.volunteers.all().order_by('firstname', 'lastname')],
            'meta': {
                'isadmin': is_admin,
                'regid': reg.id,
            },
            'stats': _get_volunteer_stats(conference),
        }), content_type='application/json')

    if request.method != 'POST':
        raise Http404()

    if 'op' not in request.POST:
        raise Http404()

    slotid = get_int_or_error(request.POST, 'slotid')
    volid = get_int_or_error(request.POST, 'volid')

    # We should always have a valid slot
    slot = get_object_or_404(VolunteerSlot, conference=conference, pk=slotid)

    err = None

    if request.POST['op'] == 'signup':
        if volid != 0:
            raise PermissionDenied("Invalid post data")
        err = _signup(request, conference, reg, is_admin, slot)
    elif request.POST['op'] == 'remove':
        err = _remove(request, conference, reg, is_admin, slot, volid)
    elif request.POST['op'] == 'confirm':
        err = _confirm(request, conference, reg, is_admin, slot, volid)
    elif request.POST['op'] == 'add':
        err = _add(request, conference, reg, is_admin, slot, volid)
    else:
        raise Http404()

    if err:
        return HttpResponse(
            json.dumps({'err': err}),
            content_type='application/json',
            status=500,
        )

    # Req-query the database to pick up any changes, and return the complete object
    slot = VolunteerSlot.objects.prefetch_related('volunteerassignment_set', 'volunteerassignment_set__reg').filter(conference=conference, pk=slot.pk)[0]
    return HttpResponse(json.dumps({
        'err': None,
        'slot': _slot_return_data(slot),
        'stats': _get_volunteer_stats(conference),
    }), content_type='application/json')


@login_required
def volunteerschedule(request, urlname, adm=False):
    try:
        (conference, can_admin, reg) = _get_conference_and_reg(request, urlname)
    except ConferenceRegistration.DoesNotExist:
        return HttpResponse("Must be registered for conference to view volunteer schedule")

    is_admin = can_admin and adm

    slots = VolunteerSlot.objects.filter(conference=conference).order_by('timerange', 'title')

    return render(request, 'confreg/volunteer_schedule.html', {
        'basetemplate': is_admin and 'confreg/confadmin_base.html' or 'confreg/volunteer_base.html',
        'conference': conference,
        'admin': is_admin,
        'can_admin': can_admin,
        'reg': reg,
        'slots': slots,
        'helplink': 'volunteers',
    })


def _signup(request, conference, reg, adm, slot):
    if VolunteerAssignment.objects.filter(slot=slot, reg=reg).exists():
        return "Already a volunteer for selected slot"
    elif slot.countvols >= slot.max_staff:
        return "Volunteer slot is already full"
    elif VolunteerAssignment.objects.filter(reg=reg, slot__timerange__overlap=slot.timerange).exists():
        return "Cannot sign up for an overlapping slot"
    else:
        a = VolunteerAssignment(slot=slot, reg=reg, vol_confirmed=True, org_confirmed=False)
        a.save()
        send_volunteer_notification(conference, a, 'Volunteer signed up', 'admin_notify_volunteer_signup.txt')


def _add(request, conference, reg, adm, slot, volid):
    addreg = get_object_or_404(ConferenceRegistration, conference=conference, id=volid)
    if VolunteerAssignment.objects.filter(slot=slot, reg=addreg).exists():
        return "Already a volunteer for selected slot"
    elif slot.countvols >= slot.max_staff:
        return "Volunteer slot is already full"
    elif VolunteerAssignment.objects.filter(reg=addreg, slot__timerange__overlap=slot.timerange).exists():
        return "Cannot add to an overlapping slot"
    else:
        VolunteerAssignment(slot=slot, reg=addreg, vol_confirmed=False, org_confirmed=True).save()


def _remove(request, conference, reg, is_admin, slot, aid):
    if is_admin:
        a = get_object_or_404(VolunteerAssignment, slot=slot, id=aid)
    else:
        a = get_object_or_404(VolunteerAssignment, slot=slot, reg=reg, id=aid)
    if a.org_confirmed and not is_admin:
        return "Cannot remove a confirmed assignment. Please contact the volunteer schedule coordinator for manual processing."
    else:
        a.delete()


def _confirm(request, conference, reg, is_admin, slot, aid):
    if is_admin:
        # Admins can make organization confirms
        a = get_object_or_404(VolunteerAssignment, slot=slot, id=aid)
        if a.org_confirmed:
            return "Assignment already confirmed"
        else:
            a.org_confirmed = True
            a.save()
    else:
        # Regular users can confirm their own sessions only
        a = get_object_or_404(VolunteerAssignment, slot=slot, reg=reg, id=aid)
        if a.vol_confirmed:
            return "Assignment already confirmed"
        else:
            a.vol_confirmed = True
            a.save()
            send_volunteer_notification(conference, a, 'Volunteer slot confirmed', 'admin_notify_volunteer_confirmed.txt')


def ical(request, urlname, token):
    conference = get_conference_or_404(urlname)
    reg = get_object_or_404(ConferenceRegistration, regtoken=token)
    assignments = VolunteerAssignment.objects.filter(reg=reg).order_by('slot__timerange')
    resp = render(request, 'confreg/volunteer_schedule.ical', {
        'conference': conference,
        'assignments': assignments,
        'now': datetime.utcnow(),
    }, content_type='text/calendar')
    resp['Content-Disposition'] = 'attachment; filename="{}_volunteer.ical"'.format(conference.urlname)
    return resp
