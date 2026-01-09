from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.http import Http404, HttpResponse
from django.contrib.auth.decorators import login_required

from postgresqleu.util.backendviews import backend_list_editor
from postgresqleu.mailqueue.backendforms import BackendMailqueueForm
from postgresqleu.mailqueue.models import QueuedMail
from postgresqleu.mailqueue.util import parse_mail_content, recursive_parse_attachments_from_message


@login_required
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
                               allow_save=False,
    )


@login_required
def view_attachment(request, queueid, attname):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    mail = get_object_or_404(QueuedMail, pk=queueid)

    msg, body, htmlbody = parse_mail_content(mail.fullmsg)
    for id, filename, contenttype, content in recursive_parse_attachments_from_message(msg, None):
        if filename == attname:
            return HttpResponse(bytes(content), content_type=contenttype)
    raise Http404("Attachment not found")
