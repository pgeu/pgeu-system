from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.db import transaction
from django.db.models import Count, Sum, F, Func
from django.conf.urls import url

from datetime import datetime

from postgresqleu.util.db import exec_to_dict

from .views import render_conference_response
from .models import Conference, ConferenceRegistration
from .models import VolunteerSlot, VolunteerAssignment
from .util import send_conference_mail


def _check_admin(request, conference):
    if request.user.is_superuser:
        return True
    else:
        return conference.administrators.filter(pk=request.user.id).exists() or conference.series.administrators.filter(pk=request.user.id).exists()


def _get_conference_and_reg(request, urlname):
    conference = get_object_or_404(Conference, urlname=urlname)
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


@login_required
@transaction.atomic
def volunteerschedule(request, urlname, adm=False):
    try:
        (conference, can_admin, reg) = _get_conference_and_reg(request, urlname)
    except ConferenceRegistration.DoesNotExist:
        return HttpResponse("Must be registered for conference to view volunteer schedule")

    is_admin = can_admin and adm

    if request.method == 'POST':
        for k, v in request.POST.items():
            if k.startswith('signup-'):
                _signup(request, conference, reg, is_admin, int(k[len('signup-'):]))
                break
            elif k.startswith('remove-'):
                pieces = [int(i) for i in k[len('remove-'):].split('-')]
                _remove(request, conference, reg, is_admin, pieces[0], pieces[1])
                break
            elif k.startswith('confirm-'):
                pieces = [int(i) for i in k[len('confirm-'):].split('-')]
                _confirm(request, conference, reg, is_admin, pieces[0], pieces[1])
                break
            elif k.startswith('add-vol-'):
                if is_admin:
                    slotid = int(k[len('add-vol-'):])
                    volid = int(v)
                    if volid != -1:
                        _add(request, conference, reg, is_admin, slotid, volid)
                    else:
                        # If it's an add of -1, there may be something else present
                        # as well, so keep searching.
                        continue
                else:
                    messages.warning(request, "Permission denied")
                break
        else:
            messages.error(request, "Unknown button pressed")
        return HttpResponseRedirect(".")

    slots = VolunteerSlot.objects.filter(conference=conference).order_by('timerange', 'title')
    allregs = conference.volunteers.all()

    stats = ConferenceRegistration.objects.filter(conference=conference) \
                                          .filter(volunteers_set=conference) \
                                          .annotate(num_assignments=Count('volunteerassignment')) \
                                          .annotate(total_time=Sum(Func(
                                              Func(F('volunteerassignment__slot__timerange'), function='upper'),
                                              Func(F('volunteerassignment__slot__timerange'), function='lower'),
                                              function='age'))) \
                                          .order_by('lastname', 'firstname')

    return render_conference_response(request, conference, 'reg', 'confreg/volunteer_schedule.html', {
        'admin': is_admin,
        'can_admin': can_admin,
        'reg': reg,
        'slots': slots,
        'allregs': allregs,
        'stats': stats,
        'rowerror': request.session.pop('rowerror', None),
    })


def _signup(request, conference, reg, adm, slotid):
    slot = get_object_or_404(VolunteerSlot, conference=conference, id=slotid)
    if VolunteerAssignment.objects.filter(slot=slot, reg=reg).exists():
        request.session['rowerror'] = [int(slotid), "Already a volunteer for selected slot"]
    elif slot.countvols >= slot.max_staff:
        request.session['rowerror'] = [int(slotid), "Volunteer slot is already full"]
    elif VolunteerAssignment.objects.filter(reg=reg, slot__timerange__overlap=slot.timerange).exists():
        request.session['rowerror'] = [int(slotid), "Cannot sign up for an overlapping slot"]
    else:
        a = VolunteerAssignment(slot=slot, reg=reg, vol_confirmed=True, org_confirmed=False)
        a.save()
        send_volunteer_notification(conference, a, 'Volunteer signed up', 'admin_notify_volunteer_signup.txt')


def _add(request, conference, reg, adm, slotid, volid):
    addreg = get_object_or_404(ConferenceRegistration, conference=conference, id=volid)
    slot = get_object_or_404(VolunteerSlot, conference=conference, id=slotid)
    if VolunteerAssignment.objects.filter(slot=slot, reg=addreg).exists():
        request.session['rowerror'] = [int(slotid), "Already a volunteer for selected slot"]
    elif slot.countvols >= slot.max_staff:
        request.session['rowerror'] = [int(slotid), "Volunteer slot is already full"]
    elif VolunteerAssignment.objects.filter(reg=addreg, slot__timerange__overlap=slot.timerange).exists():
        request.session['rowerror'] = [int(slotid), "Cannot add to an overlapping slot"]
    else:
        VolunteerAssignment(slot=slot, reg=addreg, vol_confirmed=False, org_confirmed=True).save()


def _remove(request, conference, reg, is_admin, slotid, aid):
    slot = get_object_or_404(VolunteerSlot, conference=conference, id=slotid)
    if is_admin:
        a = get_object_or_404(VolunteerAssignment, slot=slot, id=aid)
    else:
        a = get_object_or_404(VolunteerAssignment, slot=slot, reg=reg, id=aid)
    if a.org_confirmed and not is_admin:
        request.session['rowerror'] = [int(slotid), "Cannot remove a confirmed assignment. Please contact the volunteer schedule coordinator for manual processing."]
    else:
        a.delete()


def _confirm(request, conference, reg, is_admin, slotid, aid):
    slot = get_object_or_404(VolunteerSlot, conference=conference, id=slotid)
    if is_admin:
        # Admins can make organization confirms
        a = get_object_or_404(VolunteerAssignment, slot=slot, id=aid)
        if a.org_confirmed:
            messages.info(request, "Assignment already confirmed")
        else:
            a.org_confirmed = True
            a.save()
    else:
        # Regular users can confirm their own sessions only
        a = get_object_or_404(VolunteerAssignment, slot=slot, reg=reg, id=aid)
        if a.vol_confirmed:
            messages.info(request, "Assignment already confirmed")
        else:
            a.vol_confirmed = True
            a.save()
            send_volunteer_notification(conference, a, 'Volunteer slot confirmed', 'admin_notify_volunteer_confirmed.txt')


def ical(request, urlname, token):
    conference = get_object_or_404(Conference, urlname=urlname)
    reg = get_object_or_404(ConferenceRegistration, regtoken=token)
    assignments = VolunteerAssignment.objects.filter(reg=reg).order_by('slot__timerange')
    return render(request, 'confreg/volunteer_schedule.ical', {
        'conference': conference,
        'assignments': assignments,
        'now': datetime.utcnow(),
    }, content_type='text/calendar')
