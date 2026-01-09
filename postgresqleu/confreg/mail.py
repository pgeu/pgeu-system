from django.shortcuts import render
from django.utils.html import escape
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.utils import timezone
from django.forms.utils import ErrorDict

from postgresqleu.util.db import exec_to_dict, exec_to_scalar, exec_no_result
from postgresqleu.scheduler.util import trigger_immediate_job_run

from .backendforms import BackendSendEmailForm
from .models import Conference, ConferenceRegistration
from .jinjafunc import get_all_available_attributes, render_sandboxed_template


class AttendeeEmailQuerySampleMixin:
    def get_sample_attendee(self):
        ret = exec_to_dict("SELECT regid FROM ({}) WHERE regid IS NOT NULL".format(self.query), self.queryparams)
        if ret:
            return ConferenceRegistration.objects.get(pk=ret[0]['regid'])
        else:
            return None


class BaseAttendeeEmailProvider:
    trigger_job = 'confreg_send_emails'

    def __init__(self, conference, idlist):
        self.conference = conference
        self.idlist = self.process_idlist(idlist)
        self.queryparams = {'conference': conference.id if conference else None, 'idlist': self.idlist}
        self._recipients = None

    def process_idlist(self, idlist):
        return list(map(int, idlist))

    @property
    def query(self):
        return "SELECT id AS regid, attendee_id AS user_id, firstname || ' ' || lastname AS fullname, email FROM confreg_conferenceregistration WHERE conference_id=%(conference)s AND id=ANY(%(idlist)s)"

    @property
    def recipients(self):
        if self._recipients is None:
            self._recipients = self.get_recipients()
        return self._recipients

    def get_recipients(self):
        return exec_to_dict(self.query, self.queryparams)

    def get_recipient_string(self):
        return escape(", ".join([
            '{0} <{1}>{2}'.format(x['fullname'], x['email'], '' if x['regid'] else ' (No reg)')
            for x in self.recipients
        ]))

    def get_sample_attendee(self):
        return ConferenceRegistration.objects.get(pk=self.idlist[0])

    @property
    def allow_attendee_ref(self):
        return True

    def get_preview_context(self):
        context = {
            'conference': self.conference,
            'firstname': 'TestFirstName',
            'lastname': 'TestLastName',
        }
        if self.allow_attendee_ref:
            context['attendee'] = self.get_sample_attendee()
            context['firstname'] = context['attendee'].firstname
            context['lastname'] = context['attendee'].lastname
        return context

    def get_contextrefs(self):
        contextrefs = {
            'conference': Conference,
            'firstname': None,
            'lastname': None,
        }
        if self.allow_attendee_ref:
            contextrefs['attendee'] = ConferenceRegistration
        return contextrefs

    def get_initial(self):
        return {
            '_from': '{0} <{1}>'.format(self.conference.conferencename, self.conference.contactaddr),
            'recipients': self.get_recipient_string(),
            'idlist': ",".join(map(str, self.idlist)),
        }

    def insert_emails(self, sendat, subject, message):
        mailid = exec_to_scalar("INSERT INTO confreg_attendeemail (conference_id, sent, sentat, subject, message, tocheckin, tovolunteers) VALUES (%(confid)s, false, %(sentat)s, %(subject)s, %(message)s, false, false) RETURNING id", {
            'confid': self.conference.id,
            'sentat': sendat,
            'subject': subject,
            'message': message,
        })
        for r in self.recipients:
            if r['regid']:
                # Existing registration, so attach directly to attendee
                exec_no_result("INSERT INTO confreg_attendeemail_registrations (attendeemail_id, conferenceregistration_id) VALUES (%(mailid)s, %(reg)s)", {
                    'mailid': mailid,
                    'reg': r['regid'],
                })
            else:
                # No existing registration, so queue it up in case the attendee
                # might register later. We have the userid...
                exec_no_result("INSERT INTO confreg_attendeemail_pending_regs (attendeemail_id, user_id) VALUES (%(mailid)s, %(userid)s)", {
                    'mailid': mailid,
                    'userid': r['user_id'],
                })

    def prepare_form(self, form):
        pass


def attendee_email_form(request, conference, providerclass=BaseAttendeeEmailProvider, breadcrumbs=[], basetemplate='confreg/confadmin_base.html'):
    if request.method == 'POST':
        provider = providerclass(conference, request.POST['idlist'].split(','))
    else:
        if 'idlist' not in request.GET:
            raise Http404("Mandatory parameter idlist is missing")

        provider = providerclass(conference, request.GET['idlist'].split(','))

    if request.method == 'GET' and 'fieldpreview' in request.GET:
        if request.GET['fieldpreview'] != 'message':
            raise Http404()

        try:
            context = provider.get_preview_context()

            return HttpResponse(render_sandboxed_template(
                request.GET['previewval'], context,
            ))
        except Exception as e:
            return HttpResponse("Failed to render template: {}".format(e))

    contextrefs = provider.get_contextrefs()
    contextrefs = {k: None if v is None else dict(get_all_available_attributes(v)) for k, v in contextrefs.items()}

    initial = provider.get_initial()

    if request.method == 'POST':
        p = request.POST.copy()
        p['recipients'] = initial['recipients']
        form = BackendSendEmailForm(conference, contextrefs, data=p, initial=initial)
        provider.prepare_form(form)
        if form.is_valid():
            with transaction.atomic():
                provider.insert_emails(
                    form.cleaned_data['sendat'],
                    form.cleaned_data['subject'],
                    form.cleaned_data['message'],
                )

                if form.cleaned_data['sendat'] > timezone.now():
                    messages.info(request, "Email scheduled for later sending to attendees")
                else:
                    if provider.trigger_job:
                        trigger_immediate_job_run(provider.trigger_job)
                    messages.info(request, "Email sent to attendees, and added to their registration pages")

            return HttpResponseRedirect('../')
        else:
            # Form not valid. But we have a special case where this is the initial submit
            # coming in from another page, in which case we don't want to show all the
            # "this field is required" messages.
            if request.POST.get('initial_submit', None) == '1':
                # Breaks some abstractions, but taken from django/forms/forms.py
                form._errors = ErrorDict()
                form.data['sendat'] = timezone.now()
    else:
        form = BackendSendEmailForm(conference, contextrefs, initial=initial)

    return render(request, 'confreg/admin_backend_form.html', {
        'conference': conference,
        'basetemplate': basetemplate,
        'form': form,
        'what': 'new email',
        'savebutton': 'Send email',
        'cancelurl': '../',
        'breadcrumbs': breadcrumbs,
        'helplink': 'emails',
    })
