from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from postgresqleu.util.backendviews import backend_list_editor
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.util.messaging import messaging_implementations, get_messaging_class
from postgresqleu.confreg.models import ConferenceTweetQueue, MessagingProvider
from postgresqleu.confreg.backendforms import BackendSeriesMessagingForm
from postgresqleu.newsevents.backendforms import BackendNewsForm, BackendAuthorForm
from postgresqleu.newsevents.backendforms import BackendPostQueueForm


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


def edit_postqueue(request, rest):
    authenticate_backend_group(request, 'News administrators')

    return backend_list_editor(request,
                               None,
                               BackendPostQueueForm,
                               rest,
                               bypass_conference_filter=True,
                               object_queryset=ConferenceTweetQueue.objects.filter(conference__isnull=True),
                               topadmin='News',
                               return_url='/admin/',
    )


def edit_messagingproviders(request, rest):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    def _load_messaging_formclass(classname):
        return getattr(get_messaging_class(classname), 'provider_form_class', BackendSeriesMessagingForm)

    formclass = BackendSeriesMessagingForm
    u = rest and rest.rstrip('/') or rest
    if u and u != '' and u.isdigit():
        # Editing an existing one, so pick the correct subclass!
        provider = get_object_or_404(MessagingProvider, pk=u, series__isnull=True)
        formclass = _load_messaging_formclass(provider.classname)
    elif u == 'new':
        if '_newformdata' in request.POST or 'classname' in request.POST:
            if '_newformdata' in request.POST:
                c = request.POST['_newformdata'].split(':')[0]
            else:
                c = request.POST['classname']

            if c not in messaging_implementations:
                raise PermissionDenied()

            formclass = _load_messaging_formclass(c)

    # Note! Sync with confreg/backendviews.py
    formclass.no_incoming_processing = True
    formclass.verbose_name = 'news messaging provider'
    formclass.verbose_name_plural = 'news messaging providers'

    return backend_list_editor(request,
                               None,
                               formclass,
                               rest,
                               bypass_conference_filter=True,
                               object_queryset=MessagingProvider.objects.filter(series__isnull=True),
                               topadmin='News',
                               return_url='/admin/',
    )
