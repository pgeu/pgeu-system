from django.core.exceptions import PermissionDenied
from django.shortcuts import render, get_object_or_404
from django.utils.html import escape
from django.db import transaction, connection
from django.db.models import Count
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.contrib import messages
from django.conf import settings

from postgresqleu.util.backendviews import backend_list_editor, backend_process_form
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.membership.models import MembershipConfiguration, get_config, Member
from postgresqleu.membership.models import Meeting, MeetingMessageLog
from postgresqleu.membership.models import MeetingType
from postgresqleu.membership.backendforms import BackendMemberForm, BackendMeetingForm
from postgresqleu.membership.backendforms import BackendConfigForm
from postgresqleu.membership.backendforms import BackendMemberSendEmailForm

import csv
import requests


def edit_config(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    cfg, created = MembershipConfiguration.objects.get_or_create(id=1)
    return backend_process_form(request,
                                None,
                                BackendConfigForm,
                                cfg.pk,
                                allow_new=False,
                                allow_delete=False,
                                bypass_conference_filter=True,
                                cancel_url='/admin/',
                                saved_url='/admin/',
                                topadmin='Membership',
    )


def edit_member(request, rest):
    authenticate_backend_group(request, 'Membership administrators')

    return backend_list_editor(request,
                               None,
                               BackendMemberForm,
                               rest,
                               bypass_conference_filter=True,
                               allow_new=False,
                               topadmin='Membership',
                               return_url='/admin/',
    )


def sendmail(request):
    authenticate_backend_group(request, 'Membership administrators')

    if request.method == 'POST':
        idlist = list(map(int, request.POST['idlist'].split(',')))
    else:
        idlist = list(map(int, request.GET['idlist'].split(',')))

    cfg = get_config()

    recipients = Member.objects.filter(pk__in=idlist)

    initial = {
        '_from': '{0} <{1}>'.format(cfg.sender_name, cfg.sender_email),
        'recipients': escape(", ".join(['{0} <{1}>'.format(x.fullname, x.user.email) for x in recipients])),
        'idlist': ",".join(map(str, idlist)),
    }

    if request.method == 'POST':
        p = request.POST.copy()
        p['recipients'] = initial['recipients']
        form = BackendMemberSendEmailForm(data=p, initial=initial)
        if form.is_valid():
            with transaction.atomic():
                for r in recipients:
                    msgtxt = "{0}\n\n-- \nThis message was sent to members of {1}\n".format(form.cleaned_data['message'], settings.ORG_NAME)
                    send_simple_mail(cfg.sender_email,
                                     r.user.email,
                                     form.cleaned_data['subject'],
                                     msgtxt,
                                     sendername=cfg.sender_name,
                                     receivername=r.fullname,
                    )
                messages.info(request, "Email sent to %s members" % len(recipients))

            return HttpResponseRedirect("../")
    else:
        form = BackendMemberSendEmailForm(initial=initial)

    return render(request, 'confreg/admin_backend_form.html', {
        'basetemplate': 'adm/admin_base.html',
        'form': form,
        'what': 'new email',
        'savebutton': 'Send email',
        'cancelurl': '../',
        'breadcrumbs': [('../', 'Members'), ],
    })


def edit_meeting(request, rest):
    authenticate_backend_group(request, 'Membership administrators')

    return backend_list_editor(request,
                               None,
                               BackendMeetingForm,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='Membership',
                               return_url='/admin/',
    )


def meeting_log(request, meetingid):
    authenticate_backend_group(request, 'Membership administrators')

    meeting = get_object_or_404(Meeting, pk=meetingid)

    if meeting.meetingtype != MeetingType.WEB:
        messages.warning(request, "Meeting log is only available for web meetings")
        return HttpResponseRedirect("../")

    log = MeetingMessageLog.objects.select_related('sender').only('t', 'message', 'sender__fullname').filter(meeting=meeting)

    if request.method == 'POST':
        with transaction.atomic():
            curs = connection.cursor()
            curs.execute("""DELETE FROM membership_meetingmessagelog l WHERE meeting_id=%(meetingid)s AND (
 t < (SELECT min(t) FROM membership_meetingmessagelog l2 WHERE l2.meeting_id=%(meetingid)s AND l2.message='This meeting is now open')
OR
 t > (SELECT max(t) FROM membership_meetingmessagelog l3 WHERE l3.meeting_id=%(meetingid)s AND l3.message='This meeting is now finished')
)""", {'meetingid': meetingid})
            messages.info(request, 'Removed {} entries from meeting {}.'.format(curs.rowcount, meetingid))
            return HttpResponseRedirect(".")

    if request.GET.get('format', None) == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf8')
        response['Content-Disposition'] = 'attachment;filename={} log.csv'.format(meeting.name)
        c = csv.writer(response, delimiter=';')
        c.writerow(['Time', 'Sender', 'Text'])
        for l in log:
            c.writerow([l.t, l.sender.fullname if l.sender else '', l.message])
        return response
    else:
        log = list(log.extra(select={
            'inmeeting': "CASE WHEN t < (SELECT min(t) FROM membership_meetingmessagelog l2 WHERE l2.meeting_id=membership_meetingmessagelog.meeting_id AND message='This meeting is now open') OR t > (SELECT max(t) FROM membership_meetingmessagelog l3 WHERE l3.meeting_id=membership_meetingmessagelog.meeting_id AND message='This meeting is now finished') THEN false ELSE true END",
        }))
        return render(request, 'membership/meeting_log.html', {
            'meeting': meeting,
            'log': log,
            'numextra': sum(0 if l.inmeeting else 1 for l in log),
            'topadmin': 'Membership',
            'breadcrumbs': (
                ('/admin/membership/meetings/', 'Meetings'),
                ('/admin/membership/meetings/{}/'.format(meeting.pk), meeting.name),
            ),
        })


def meeting_attendees(request, meetingid):
    authenticate_backend_group(request, 'Membership administrators')

    meeting = get_object_or_404(Meeting, pk=meetingid)

    if meeting.meetingtype != MeetingType.WEB:
        messages.warning(request, "Meeting log is only available for web meetings")
        return HttpResponseRedirect("../")

    # Django and multi-colun joins.. *sigh*. Let's make it a manual subquery instead
    # because SQL is way easier than the django ORM...
    attendees = Member.objects.only('fullname', 'user__username').select_related('user').filter(
        membermeetingkey__meeting=meetingid,
        membermeetingkey__allowrejoin=True,
    ).extra(select={
        'messagecount': '(SELECT count(*) FROM membership_meetingmessagelog l WHERE l.meeting_id=membership_membermeetingkey.meeting_id AND l.sender_id=membership_member.user_id)',
    }).order_by('fullname')

    return render(request, 'membership/meeting_attendees.html', {
        'meeting': meeting,
        'attendees': attendees,
        'topadmin': 'Membership',
        'breadcrumbs': (
            ('/admin/membership/meetings/', 'Meetings'),
            ('/admin/membership/meetings/{}/'.format(meeting.pk), meeting.name),
        ),
    })


def meetingserverstatus(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    if not settings.MEETINGS_STATUS_BASE_URL:
        raise Http404()

    try:
        if settings.MEETINGS_STATUS_BASE_URL.startswith('/'):
            import requests_unixsocket
            with requests_unixsocket.Session() as s:
                r = s.get("http+unix://{}/__meetingstatus".format(settings.MEETINGS_STATUS_BASE_URL.replace('/', '%2F')), timeout=5)
        else:
            r = requests.get("{}/__meetingstatus".format(settings.MEETINGS_STATUS_BASE_URL), timeout=5)
        r.raise_for_status()
        error = None
    except Exception as e:
        error = str(e)

    return render(request, 'membership/meeting_server_status.html', {
        'status': None if error else r.json(),
        'error': error,
        'topadmin': 'Membership',
    })
