from django.core.exceptions import PermissionDenied
from postgresqleu.util.middleware import RedirectException
from django.conf import settings

import urllib.parse


PERMISSION_GROUPS = (
    'Invoice managers',
    'News administrators',
    'Membership administrators',
    'Election administrators',
)


def authenticate_backend_group(request, groupname):
    if not request.user.is_authenticated:
        raise RedirectException("{0}?{1}".format(settings.LOGIN_URL, urllib.parse.urlencode({'next': request.build_absolute_uri()})))

    if groupname not in PERMISSION_GROUPS:
        raise PermissionDenied("Group name not known")

    if request.user.is_superuser:
        return
    if request.user.groups.filter(name=groupname).exists():
        return

    raise PermissionDenied("Access denied")
