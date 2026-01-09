from django.core.exceptions import PermissionDenied
from django.shortcuts import render, get_object_or_404
from django.utils.html import escape
from django.utils import timezone
from django.db import transaction, connection
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.contrib import messages
from django.conf import settings

from postgresqleu.util.backendviews import backend_list_editor, backend_process_form
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.mailqueue.util import send_template_mail
from postgresqleu.membership.models import MembershipConfiguration, get_config, Member
from postgresqleu.membership.models import MemberMail
from postgresqleu.membership.models import Meeting, MeetingMessageLog
from postgresqleu.membership.models import MeetingType
from postgresqleu.membership.backendforms import BackendMemberForm, BackendMeetingForm
from postgresqleu.membership.backendforms import BackendConfigForm
from postgresqleu.util.time import today_global
from postgresqleu.confreg.mail import attendee_email_form, BaseAttendeeEmailProvider, AttendeeEmailQuerySampleMixin

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


def member_email_list(request):
    authenticate_backend_group(request, 'Membership administrators')

    return render(request, 'membership/admin_email_list.html', {
        'mails': MemberMail.objects.only('sentat', 'subject').order_by('-sentat'),
        'helplink': 'membership',
        'breadcrumbs': [('../../', 'Membership'), ],
    })


def member_email(request, mailid):
    authenticate_backend_group(request, 'Membership administrators')

    mail = get_object_or_404(MemberMail, pk=mailid)
    recipients = Member.objects.select_related('user').filter(membermail=mail)

    return render(request, 'membership/admin_email_view.html', {
        'mail': mail,
        'recipients': recipients,
        'helplink': 'membership',
        'breadcrumbs': [('/admin/', 'Membership'), ('/admin/membership/emails/', 'Member emails')],
    })


def sendmail(request):
    authenticate_backend_group(request, 'Membership administrators')

    cfg = get_config()

    class MemberEmailProvider(AttendeeEmailQuerySampleMixin, BaseAttendeeEmailProvider):
        mailtemplate = 'membership/mail/member_mail.txt'
        trigger_job = 'membership_send_emails'

        @property
        def query(self):
            if self.idlist == ['allactive']:
                return "SELECT user_id AS regid, fullname FROM membership_member WHERE paiduntil >= CURRENT_TIMESTAMP"
            else:
                return "SELECT user_id AS regid, fullname FROM membership_member WHERE user_id=ANY(%(idlist)s)"

        def process_idlist(self, idlist):
            if idlist == ['allactive']:
                return idlist
            else:
                return super().process_idlist(idlist)

        def get_recipient_string(self):
            return ", ".join(m['fullname'] for m in self.recipients)

        def get_initial(self):
            return {
                '_from': '{} <{}>'.format(cfg.sender_name, cfg.sender_email),
                'recipients': self.get_recipient_string(),
                'idlist': ",".join(map(str, self.idlist))
            }

        def get_contextrefs(self):
            return {
                'member': Member,
            }

        def get_preview_context(self):
            if self.idlist == ['allactive']:
                try:
                    member = Member.objects.filter(paiduntil__gte=today_global())[1]
                except IndexError:
                    member = None
            else:
                member = Member.objects.get(pk=self.idlist[0])
            return {
                'member': member,
            }

        def prepare_form(self, form):
            # No subject prefix here
            form.fields['subject'].help_text = ''

        def insert_emails(self, sendat, subject, message):
            mail = MemberMail(
                sentat=sendat,
                sentfrom='{} <{}>'.format(cfg.sender_name, cfg.sender_email),
                subject=subject,
                message=message,
            )
            mail.save()
            if self.idlist == ['allactive']:
                mail.sentto.set(Member.objects.filter(paiduntil__gte=today_global()))
            else:
                for id in self.idlist:
                    mail.sentto.add(id)
            mail.save()

    return attendee_email_form(request, None, MemberEmailProvider, basetemplate='adm/admin_base.html', breadcrumbs=(
        ('../../members/', 'Membership'),
    ))


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
        for line in log:
            c.writerow([line.t, line.sender.fullname if line.sender else '', line.message])
        return response
    else:
        log = list(log.extra(select={
            'inmeeting': "CASE WHEN t < (SELECT min(t) FROM membership_meetingmessagelog l2 WHERE l2.meeting_id=membership_meetingmessagelog.meeting_id AND message='This meeting is now open') OR t > (SELECT max(t) FROM membership_meetingmessagelog l3 WHERE l3.meeting_id=membership_meetingmessagelog.meeting_id AND message='This meeting is now finished') THEN false ELSE true END",
        }))
        return render(request, 'membership/meeting_log.html', {
            'meeting': meeting,
            'log': log,
            'numextra': sum(0 if line.inmeeting else 1 for line in log),
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
