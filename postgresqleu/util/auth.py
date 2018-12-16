from django.core.exceptions import PermissionDenied
from postgresqleu.util.middleware import RedirectException
from django.conf import settings

import urllib


def authenticate_backend_group(request, groupname):
    if not request.user.is_authenticated:
        raise RedirectException("{0}?{1}".format(settings.LOGIN_URL, urllib.urlencode({'next': request.build_absolute_uri()})))

    if request.user.is_superuser:
        return
    if request.user.groups.filter(name=groupname).exists():
        return

    raise PermissionDenied("Access denied")
