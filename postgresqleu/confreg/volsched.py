from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.contrib import messages
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.db import transaction
from django.db.models import Count, Sum, F, Func

from datetime import datetime

from views import render_conference_response
from models import Conference, ConferenceRegistration
from models import VolunteerSlot, VolunteerAssignment


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


@login_required
def volunteerschedule(request, urlname, adm=False):
    try:
        (conference, can_admin, reg) = _get_conference_and_reg(request, urlname)
    except ConferenceRegistration.DoesNotExist:
        return HttpResponse("Must be registered for conference to view volunteer schedule")

    slots = VolunteerSlot.objects.filter(conference=conference).order_by('timerange', 'title')
    allregs = conference.volunteers.all()

    is_admin = can_admin and adm

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


@login_required
@transaction.atomic
def signup(request, urlname, slotid, adm=False):
    (conference, is_admin, reg) = _get_conference_and_reg(request, urlname)

    slot = get_object_or_404(VolunteerSlot, conference=conference, id=slotid)
    if VolunteerAssignment.objects.filter(slot=slot, reg=reg).exists():
        request.session['rowerror'] = [int(slotid), "Already a volunteer for selected slot"]
    elif slot.countvols >= slot.max_staff:
        request.session['rowerror'] = [int(slotid), "Volunteer slot is already full"]
    elif VolunteerAssignment.objects.filter(reg=reg, slot__timerange__overlap=slot.timerange).exists():
        request.session['rowerror'] = [int(slotid), "Cannot sign up for an overlapping slot"]
    else:
        VolunteerAssignment(slot=slot, reg=reg, vol_confirmed=True, org_confirmed=False).save()
    return HttpResponseRedirect('../..')


@login_required
@transaction.atomic
def add(request, urlname, slotid, regid, adm=False):
    (conference, is_admin, reg) = _get_conference_and_reg(request, urlname)
    if not is_admin:
        return HttpResponseRedirect("../..")

    addreg = get_object_or_404(ConferenceRegistration, conference=conference, id=regid)
    slot = get_object_or_404(VolunteerSlot, conference=conference, id=slotid)
    if VolunteerAssignment.objects.filter(slot=slot, reg=addreg).exists():
        request.session['rowerror'] = [int(slotid), "Already a volunteer for selected slot"]
    elif slot.countvols >= slot.max_staff:
        request.session['rowerror'] = [int(slotid), "Volunteer slot is already full"]
    elif VolunteerAssignment.objects.filter(reg=addreg, slot__timerange__overlap=slot.timerange).exists():
        request.session['rowerror'] = [int(slotid), "Cannot add to an overlapping slot"]
    else:
        VolunteerAssignment(slot=slot, reg=addreg, vol_confirmed=False, org_confirmed=True).save()
    return HttpResponseRedirect('../..')


@login_required
@transaction.atomic
def remove(request, urlname, slotid, aid, adm=False):
    (conference, is_admin, reg) = _get_conference_and_reg(request, urlname)

    slot = get_object_or_404(VolunteerSlot, conference=conference, id=slotid)
    if is_admin:
        a = get_object_or_404(VolunteerAssignment, slot=slot, id=aid)
    else:
        a = get_object_or_404(VolunteerAssignment, slot=slot, reg=reg, id=aid)
    if a.org_confirmed and not is_admin:
        request.session['rowerror'] = [int(slotid), "Cannot remove a confirmed assignment. Please contact the volunteer schedule coordinator for manual processing."]
    else:
        a.delete()
    return HttpResponseRedirect('../..')


@login_required
@transaction.atomic
def confirm(request, urlname, slotid, aid, adm=False):
    (conference, is_admin, reg) = _get_conference_and_reg(request, urlname)

    slot = get_object_or_404(VolunteerSlot, conference=conference, id=slotid)
    if is_admin and adm:
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
    return HttpResponseRedirect('../..')


def ical(request, urlname, token):
    conference = get_object_or_404(Conference, urlname=urlname)
    reg = get_object_or_404(ConferenceRegistration, regtoken=token)
    assignments = VolunteerAssignment.objects.filter(reg=reg).order_by('slot__timerange')
    return render(request, 'confreg/volunteer_schedule.ical', {
        'conference': conference,
        'assignments': assignments,
        'now': datetime.utcnow(),
    }, content_type='text/calendar')


from django.conf.urls import url

urlpatterns = [
    url(r'^$', volunteerschedule),
    url(r'^signup/(?P<slotid>\d+)/$', signup),
    url(r'^remove/(?P<slotid>\d+)-(?P<aid>\d+)/$', remove),
    url(r'^confirm/(?P<slotid>\d+)-(?P<aid>\d+)/$', confirm),
    url(r'^add/(?P<slotid>\d+)-(?P<regid>\d+)/$', add),
    url(r'^ical/(?P<token>[a-z0-9]{64})/$', ical),
]
