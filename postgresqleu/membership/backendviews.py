from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils.html import escape
from django.db import transaction
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.conf import settings

from postgresqleu.util.backendviews import backend_list_editor, backend_process_form
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.membership.models import MembershipConfiguration, get_config, Member
from postgresqleu.membership.backendforms import BackendMemberForm, BackendMeetingForm
from postgresqleu.membership.backendforms import BackendConfigForm
from postgresqleu.membership.backendforms import BackendMemberSendEmailForm


def edit_config(request):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    cfg = MembershipConfiguration.objects.get(id=1)
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
