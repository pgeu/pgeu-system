from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Member, MemberLog, Meeting, MemberMeetingKey, get_config
from .models import MeetingType
from .forms import MemberForm, ProxyVoterForm

from postgresqleu.util.random import generate_random_token
from postgresqleu.util.time import today_global
from postgresqleu.invoices.util import InvoiceManager, InvoicePresentationWrapper
from postgresqleu.invoices.models import InvoiceProcessor

from datetime import datetime, timedelta
import json
import base64
import os


@login_required
@transaction.atomic
def home(request):
    try:
        member = Member.objects.get(user=request.user)
        registration_complete = True

        # We have a batch job that expires members, but do it here as well to make sure
        # the web is up to date with information if necessary.
        if member.paiduntil and member.paiduntil < today_global():
            MemberLog(member=member,
                      timestamp=timezone.now(),
                      message="Membership expired").save()
            member.membersince = None
            member.paiduntil = None
            member.save()

    except Member.DoesNotExist:
        # No record yet, so we create one. Base the information on whatever we
        # have already.
        member = Member(user=request.user, fullname="{0} {1}".format(request.user.first_name, request.user.last_name))
        registration_complete = False

    cfg = get_config()

    if request.method == "POST":
        if request.POST["submit"] == "Generate invoice":
            # Generate an invoice for the user
            if member.activeinvoice:
                raise Exception("This should not happen - generating invoice when one already exists!")

            manager = InvoiceManager()
            processor = InvoiceProcessor.objects.get(processorname="membership processor")
            invoicerows = [('%s - %s years membership - %s' % (settings.ORG_NAME, cfg.membership_years, request.user.email), 1, cfg.membership_cost, None), ]
            member.activeinvoice = manager.create_invoice(
                request.user,
                request.user.email,
                request.user.first_name + ' ' + request.user.last_name,
                '',  # We don't have an address
                '%s membership for %s' % (settings.ORG_NAME, request.user.email),
                timezone.now(),
                timezone.now(),
                invoicerows,
                processor=processor,
                processorid=member.pk,
                canceltime=timezone.now() + timedelta(days=7),
                accounting_account=settings.ACCOUNTING_MEMBERSHIP_ACCOUNT,
                paymentmethods=cfg.paymentmethods.all(),
                )
            member.activeinvoice.save()
            member.save()

            # We'll redirect back to the same page, so make sure
            # someone doing say a hard refresh on the page doesn't
            # cause weird things to happen.
            return HttpResponseRedirect('/membership/')

        form = MemberForm(data=request.POST, instance=member)
        if form.is_valid():
            member = form.save(commit=False)
            member.user = request.user
            member.save()
            if not registration_complete:
                MemberLog(member=member,
                          timestamp=timezone.now(),
                          message="Registration received, awaiting payment").save()
                registration_complete = True  # So we show the payment info!
            elif form.has_changed():
                # Figure out what changed
                MemberLog(member=member,
                          timestamp=timezone.now(),
                          message="Modified registration data for field(s): %s" % (", ".join(form.changed_data)),
                          ).save()
            return HttpResponseRedirect(".")
    else:
        form = MemberForm(instance=member)

    logdata = MemberLog.objects.filter(member=member).order_by('-timestamp')[:30]

    return render(request, 'membership/index.html', {
        'form': form,
        'member': member,
        'invoice': InvoicePresentationWrapper(member.activeinvoice, "%s/membership/" % settings.SITEBASE),
        'registration_complete': registration_complete,
        'logdata': logdata,
        'amount': cfg.membership_cost,
        'cancelurl': '/account/',
    })


def userlist(request):
    members = Member.objects.select_related('country').filter(listed=True, paiduntil__gt=timezone.now()).order_by('fullname')
    return render(request, 'community/userlist.html', {
        'members': members,
    })


@login_required
def meetings(request):
    # Only available for actual members
    member = get_object_or_404(Member, user=request.user)
    q = Q(dateandtime__gte=timezone.now() - timedelta(hours=4)) & (Q(allmembers=True) | Q(members=member))
    meetings = Meeting.objects.filter(q).distinct().order_by('dateandtime')

    meetinginfo = [{
        'id': m.id,
        'name': m.name,
        'dateandtime': m.dateandtime,
        'key': m.get_key_for(member),
        } for m in meetings]

    return render(request, 'membership/meetings.html', {
        'active': member.paiduntil and member.paiduntil >= today_global(),
        'member': member,
        'meetings': meetinginfo,
        })


def membership_error_response(request, msg):
    return render(request, 'membership/error.html', {
        'message': msg,
    })


@transaction.atomic
def _meeting(request, member, meeting, isproxy):
    if not (member.paiduntil and member.paiduntil >= today_global()):
        return membership_error_response(request, "Your membership is not active")

    if not meeting.allmembers:
        if not meeting.members.filter(pk=member.pk).exists():
            return membership_error_response(request, "Access denied.")

    # Allow four hours in the past, just in case
    if meeting.dateandtime + timedelta(hours=4) < timezone.now():
        return membership_error_response(request, "Meeting is in the past.")

    if member.paiduntil < timezone.localdate(meeting.dateandtime):
        return membership_error_response(request, "Your membership expires before the meeting")

    # All is well with this member. Generate a key if necessary
    (key, created) = MemberMeetingKey.objects.get_or_create(member=member, meeting=meeting)
    if created:
        # New key!
        key.key = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b'=').decode('utf8')
        key.save()

    if key.proxyname and not isproxy:
        return membership_error_response(request, "You have assigned a proxy attendee for this meeting ({0}). This means you cannot attend the meeting yourself.".format(key.proxyname))

    if meeting.meetingtype == MeetingType.WEB:
        return render(request, 'membership/webmeeting.html', {
            'member': member,
            'meeting': meeting,
            'key': key,
            'is_admin': request.user.is_superuser,
        })
    elif meeting.meetingtype == MeetingType.IRC:
        return render(request, 'membership/meeting.html', {
            'member': member,
            'meeting': meeting,
            'key': key,
        })
    else:
        raise Exception("Unknown meeting type")


@login_required
def meeting(request, meetingid):
    # View a single meeting
    meeting = get_object_or_404(Meeting, pk=meetingid)
    member = get_object_or_404(Member, user=request.user)
    return _meeting(request, member, meeting, False)


def meeting_by_key(request, meetingid, token):
    key = get_object_or_404(MemberMeetingKey, proxyaccesskey=token)
    return _meeting(request, key.member, key.meeting, True)


def _webmeeting(request, key):
    if not settings.MEETINGS_WS_BASE_URL:
        raise Http404

    is_admin = key.meeting.meetingadmins.filter(pk=key.member.pk).exists()

    return render(request, 'membership/webmeeting_implementation.html', {
        'meeting': key.meeting,
        'member': key.member,
        'key': key,
        'is_admin': is_admin,
        'wsbaseurl': settings.MEETINGS_WS_BASE_URL.rstrip("/"),
    })


@login_required
def webmeeting(request, meetingid):
    meeting = get_object_or_404(Meeting, pk=meetingid)
    member = get_object_or_404(Member, user=request.user)

    # At this point the user must have a key for this meeting. If not, we redirect them back to
    # get one. And if they have a key, the permissions checks have been done there.
    try:
        key = MemberMeetingKey.objects.get(member=member, meeting=meeting)
    except MemberMeetingKey.DoesNotExist:
        return HttpResponseRedirect("../")

    # If a proxy is assigned, the original member is not allowed to join
    if key.proxyaccesskey:
        return HttpResponseRedirect("../")

    return _webmeeting(request, key)


def webmeeting_by_key(request, meetingid, token):
    key = get_object_or_404(MemberMeetingKey, proxyaccesskey=token)
    return _webmeeting(request, key)


def meeting_ical(request, meetingid):
    # Get the ical info about a meeting
    meeting = get_object_or_404(Meeting, pk=meetingid)
    member = get_object_or_404(Member, user=request.user)

    resp = render(request, 'membership/meeting.ical', {
        'meeting': meeting,
        'member': member,
        'starttime': meeting.dateandtime,
        'endtime': meeting.dateandtime + timedelta(hours=1),  # We don't track length of meetings
        'now': datetime.now(),
    }, content_type='text/calendar')
    resp['Content-Disposition'] = 'attachment; filename="meeting.ical"'
    return resp


@login_required
@transaction.atomic
def meeting_proxy(request, meetingid):
    # Assign proxy voter for meeting
    meeting = get_object_or_404(Meeting, pk=meetingid)
    member = get_object_or_404(Member, user=request.user)

    if not (member.paiduntil and member.paiduntil >= today_global()):
        return membership_error_response(request, "Your membership is not active")

    if not meeting.allmembers:
        if not meeting.members.filter(pk=member.pk).exists():
            return membership_error_response(request, "Access denied.")

    if member.paiduntil < timezone.localdate(meeting.dateandtime):
        return membership_error_response(request, "Your membership expires before the meeting")

    if meeting.dateandtime <= timezone.now():
        return membership_error_response(request, "This meeting has already started, you can no longer edit the proxy")

    # Do we have one already?
    try:
        key = MemberMeetingKey.objects.get(member=member, meeting=meeting)
    except MemberMeetingKey.DoesNotExist:
        key = MemberMeetingKey()
        key.meeting = meeting
        key.member = member

    initial = {
        'name': key.proxyname,
    }

    if request.method == 'POST':
        form = ProxyVoterForm(initial=initial, data=request.POST)
        if form.is_valid():
            if form.cleaned_data['name']:
                key.proxyname = form.cleaned_data['name']
                key.proxyaccesskey = generate_random_token()
                key.key = base64.urlsafe_b64encode(os.urandom(40)).rstrip(b'=').decode('utf8')
                key.save()
                MemberLog(member=member,
                          timestamp=timezone.now(),
                          message="Assigned {0} as proxy voter in {1}".format(key.proxyname, meeting.name)
                ).save()
                return HttpResponseRedirect('.')
            else:
                key.proxyname = None
                key.proxyaccesskey = None
                key.save()
                MemberLog(member=member,
                          timestamp=timezone.now(),
                          message="Canceled proxy voting in {0}".format(meeting.name)
                ).save()
                return HttpResponseRedirect("../../")
    else:
        form = ProxyVoterForm(initial=initial)

    return render(request, 'membership/meetingproxy.html', {
        'member': member,
        'meeting': meeting,
        'key': key,
        'form': form,
        })


# API calls from meeting bot
def meetingcode(request):
    if 's' not in request.GET or 'm' not in request.GET:
        raise Http404("Mandatory parameter is missing")
    secret = request.GET['s']
    meetingid = request.GET['m']

    try:
        key = MemberMeetingKey.objects.get(key=secret, meeting__pk=meetingid)
        if key.meeting.dateandtime + timedelta(hours=4) < timezone.now():
            return HttpResponse(json.dumps({'err': 'This meeting is not open for signing in yet.'}),
                                content_type='application/json')
        member = key.member
    except MemberMeetingKey.DoesNotExist:
        return HttpResponse(json.dumps({'err': 'Authentication key not found. Please see %s/membership/meetings/ to get your correct key!' % settings.SITEBASE}),
                            content_type='application/json')

    if key.proxyname:
        name = "{0} (proxy for {1})".format(key.proxyname, member.fullname)
    else:
        name = member.fullname

    # Return a JSON object with information about the member
    return HttpResponse(json.dumps({'username': member.user.username,
                                    'email': member.user.email,
                                    'name': name,
    }), content_type='application/json')
