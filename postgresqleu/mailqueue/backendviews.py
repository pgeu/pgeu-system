from django.core.exceptions import PermissionDenied

from postgresqleu.util.backendviews import backend_list_editor
from postgresqleu.mailqueue.backendforms import BackendMailqueueForm


def edit_mailqueue(request, rest):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    return backend_list_editor(request,
                               None,
                               BackendMailqueueForm,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='Mailqueue',
                               return_url='/admin/',
                               allow_new=False,
    )
