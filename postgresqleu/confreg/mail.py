from django.shortcuts import render
from django.utils.html import escape
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.contrib import messages

from postgresqleu.util.db import exec_to_dict, exec_to_scalar, exec_no_result

from .util import send_conference_mail
from .backendforms import BackendSendEmailForm


def attendee_email_form(request, conference, query=None, breadcrumbs=[], template='confreg/mail/attendee_mail.txt', extracontext={}, strings=False):
    if request.method == 'POST':
        if strings:
            idlist = request.POST['idlist'].split(',')
        else:
            idlist = list(map(int, request.POST['idlist'].split(',')))
    else:
        if 'idlist' not in request.GET:
            raise Http404("Mandatory parameter idlist is missing")

        if strings:
            idlist = request.GET['idlist'].split(',')
        else:
            idlist = list(map(int, request.GET['idlist'].split(',')))

    queryparams = {'conference': conference.id, 'idlist': idlist}
    if query is None:
        query = "SELECT id AS regid, attendee_id AS user_id, firstname || ' ' || lastname AS fullname, email FROM confreg_conferenceregistration WHERE conference_id=%(conference)s AND id=ANY(%(idlist)s)"
    elif callable(query):
        query, queryparams = query(idlist)

    recipients = exec_to_dict(query, queryparams)

    initial = {
        '_from': '{0} <{1}>'.format(conference.conferencename, conference.contactaddr),
        'recipients': escape(", ".join(['{0} <{1}>'.format(x['fullname'], x['email']) for x in recipients])),
        'idlist': ",".join(map(str, idlist)),
        'storeonregpage': True,
    }

    if request.method == 'POST':
        p = request.POST.copy()
        p['recipients'] = initial['recipients']
        form = BackendSendEmailForm(conference, data=p, initial=initial)
        if form.is_valid():
            with transaction.atomic():
                if form.cleaned_data['storeonregpage']:
                    mailid = exec_to_scalar("INSERT INTO confreg_attendeemail (conference_id, sentat, subject, message, tocheckin, tovolunteers) VALUES (%(confid)s, CURRENT_TIMESTAMP, %(subject)s, %(message)s, false, false) RETURNING id", {
                        'confid': conference.id,
                        'subject': form.cleaned_data['subject'],
                        'message': form.cleaned_data['message'],
                    })
                for r in recipients:
                    send_conference_mail(conference,
                                         r['email'],
                                         form.cleaned_data['subject'],
                                         template,
                                         {
                                             'body': form.cleaned_data['message'],
                                             'linkback': form.cleaned_data['storeonregpage'],
                                         } | extracontext,
                                         receivername=r['fullname'],
                    )

                    if form.cleaned_data['storeonregpage']:
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
                if form.cleaned_data['storeonregpage']:
                    messages.info(request, "Email sent to %s attendees, and added to their registration pages when possible" % len(recipients))
                else:
                    messages.info(request, "Email sent to %s attendees" % len(recipients))

            return HttpResponseRedirect('../')
    else:
        form = BackendSendEmailForm(conference, initial=initial)

    return render(request, 'confreg/admin_backend_form.html', {
        'conference': conference,
        'basetemplate': 'confreg/confadmin_base.html',
        'form': form,
        'what': 'new email',
        'savebutton': 'Send email',
        'cancelurl': '../',
        'breadcrumbs': breadcrumbs,
    })
