from postgresqleu.util.backendviews import backend_list_editor, backend_process_form
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.membership.models import MembershipConfiguration
from postgresqleu.membership.backendforms import BackendMemberForm, BackendMeetingForm
from postgresqleu.membership.backendforms import BackendConfigForm


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
