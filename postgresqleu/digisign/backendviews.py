from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render

import base64
import io
import json

from postgresqleu.util.backendviews import backend_list_editor
from postgresqleu.util.versionutil import fitz_get_page_png
from postgresqleu.digisign.models import DigisignProvider, DigisignLog
from postgresqleu.digisign.backendforms import BackendProviderForm
from postgresqleu.digisign.util import digisign_providers
from postgresqleu.digisign.pdfutil import fill_pdf_fields


def edit_providers(request, rest):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    def _load_formclass(classname):
        pieces = classname.split('.')
        modname = '.'.join(pieces[:-1])
        classname = pieces[-1]
        mod = __import__(modname, fromlist=[classname, ])
        if hasattr(getattr(mod, classname), 'backend_form_class'):
            return getattr(mod, classname).backend_form_class
        else:
            return BackendProviderForm

    u = rest and rest.rstrip('/') or rest
    if u and u != '' and u.isdigit():
        p = get_object_or_404(DigisignProvider, pk=u)
        formclass = _load_formclass(p.classname)
    elif u == 'new':
        if '_newformdata' in request.POST or 'classname' in request.POST:
            c = request.POST['_newformdata' if '_newformdata' in request.POST else 'classname']
            if c not in digisign_providers:
                raise PermissionDenied()

            formclass = _load_formclass(c)
        else:
            formclass = BackendProviderForm
    else:
        formclass = BackendProviderForm

    return backend_list_editor(request,
                               None,
                               formclass,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='Digital signatures',
                               return_url='/admin/',
    )


def view_provider_log(request, providerid):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    provider = get_object_or_404(DigisignProvider, pk=providerid)

    return render(request, 'digisign/digisign_backend_log.html', {
        'log': DigisignLog.objects.filter(provider=provider).order_by('-id')[:100],
        'hasdetails': provider.get_implementation().has_log_details,
        'breadcrumbs': [
            ('/admin/digisign/providers/', 'Digital signature providers'),
            ('/admin/digisign/providers/{}/'.format(provider.id), provider.name),
        ]
    })


def view_provider_log_details(request, providerid, logid):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    provider = get_object_or_404(DigisignProvider, pk=providerid)
    log = get_object_or_404(DigisignLog, provider=provider, pk=logid)

    return render(request, 'digisign/digisign_backend_log_details.html', {
        'log': log,
        'breadcrumbs': [
            ('/admin/digisign/providers/', 'Digital signature providers'),
            ('/admin/digisign/providers/{}/'.format(provider.id), provider.name),
            ('/admin/digisign/providers/{}/log/'.format(provider.id), "Log"),
        ]
    })


def pdf_field_editor(request, conference, pdf, available_fields, fielddata, savecallback=None, breadcrumbs=[]):
    import fitz

    if request.method == 'GET' and request.GET.get('current', '0') == '1':
        return HttpResponse(
            json.dumps(fielddata),
            content_type='application/json',
            status=200,
        )
    elif request.method == 'POST' and 'application/json' in request.META['CONTENT_TYPE']:
        # Postback to save all fields
        try:
            postdata = json.loads(request.body.decode())
        except json.decoder.JSONDecodeError:
            return HttpResponse("Invalid json", status=400)

        newdata = {
            'fields': [],
            'fontsize': int(postdata['fontsize']),
        }
        fieldnames = [fn for fn, fd in available_fields]
        for f in postdata['fields']:
            if f['field'] in fieldnames:
                newdata['fields'].append({
                    'field': f['field'],
                    'page': int(f['page']),
                    'x': int(f['x']),
                    'y': int(f['y']),
                })
            else:
                return HttpResponse('Invalid field {}'.format(f['field']), status=400)

        newdata['fields'] = sorted(newdata['fields'], key=lambda f: f['page'])
        savecallback(fielddata | newdata)
        return HttpResponse(json.dumps({'status': 'OK'}), content_type="application/json", status=200)

    # Or we render the base page

    # This is inefficient as hell, but we hope not to have huge PDFs :) Turn the PDF into
    # one PNG for each page.
    pdf = fitz.open('pdf', bytes(pdf))
    pages = []
    pages = [(pagenum, base64.b64encode(fitz_get_page_png(page)).decode()) for pagenum, page in enumerate(pdf.pages())]

    return render(request, 'digisign/pdf_field_editor.html', {
        'conference': conference,
        'breadcrumbs': breadcrumbs,
        'pages': pages,
        'fields': available_fields,
    })


def pdf_field_preview(request, conference, pdf, available_fields, fielddata):
    pdf = fill_pdf_fields(pdf, available_fields, fielddata)

    resp = HttpResponse(content_type='application/pdf')
    resp.write(pdf)
    return resp
