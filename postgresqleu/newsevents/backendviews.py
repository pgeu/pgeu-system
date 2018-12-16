from django.core.exceptions import PermissionDenied

from postgresqleu.util.backendviews import backend_list_editor
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.newsevents.backendforms import BackendNewsForm, BackendAuthorForm


def edit_news(request, rest):
    authenticate_backend_group(request, 'News administrators')

    return backend_list_editor(request,
                               None,
                               BackendNewsForm,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='News',
                               return_url='/admin/',
    )


def edit_author(request, rest):
    # Require superuser to add new author profiles, since amongst other things it
    # can browse all users.
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    return backend_list_editor(request,
                               None,
                               BackendAuthorForm,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='News',
                               return_url='/admin/',
    )
