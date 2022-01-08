from django.shortcuts import render
from django.http import HttpResponseForbidden, Http404
from django.conf import settings
from django.utils.safestring import mark_safe
from django.contrib.auth.decorators import login_required
from django.db.models import Q

import codecs
import os
import re
import markdown

from postgresqleu.confreg.models import Conference, ConferenceSeries
from postgresqleu.util.auth import PERMISSION_GROUPS


reTitle = re.compile('<h1>([^<]+)</h1>')

_reSvgInline = re.compile(r'<img alt="([^"]+)" src="([^"]+)\.svg" />')


def _replaceSvgInline(m, section):
    # Group 1 = alt text
    # Group 2 = filename excluding svg
    filename = 'docs/{0}/{1}.svg'.format(section, m.group(2))
    if not os.path.isfile(filename):
        return m.group(0)

    with codecs.open(filename, 'r', 'utf8') as f:
        return f.read()


@login_required
def docspage(request, page=None):
    # Allow a person who has *any* permissions on a conference to read the docs,
    # because, well, they are docs.
    # Since we also have docs for non-conference things, check for membership
    # of *any* permissions groups.
    if not request.user.is_superuser:
        q = Q(administrators=request.user) | Q(talkvoters=request.user)
        if not Conference.objects.filter(q).exists() and \
           not ConferenceSeries.objects.filter(administrators=request.user).exists() and \
           not request.user.groups.filter(name__in=PERMISSION_GROUPS).exists():
            return HttpResponseForbidden("Access denied")

    if page:
        page = page.rstrip('/')
        urlpage = page
    else:
        page = "index"
        urlpage = ''

    # Do we have the actual docs file?
    # It's safe to just put the filename in here, because the regexp in urls.py ensures
    # that we can not get into a path traversal case.
    # The file can be in different subdirectories though, so enumerate them
    for d in os.listdir('docs/'):
        filename = 'docs/{0}/{1}.md'.format(d, page)
        if os.path.isfile(filename):
            section = d
            break
    else:
        raise Http404()

    with open(filename) as f:
        md = markdown.Markdown(extensions=['markdown.extensions.def_list', 'markdown.extensions.fenced_code'])
        contents = md.convert(f.read())
    contents = _reSvgInline.sub(lambda m: _replaceSvgInline(m, section), contents)

    # Find the title
    m = reTitle.search(contents)
    if m:
        title = m.group(1)
    else:
        title = '{0} Administration'.format(settings.ORG_SHORTNAME)

    return render(request, 'confreg/admin_backend_docpage.html', {
        'basepage': 'adm/admin_base.html',
        'page': page,
        'contents': contents,
        'title': mark_safe(title),
        'urlpage': urlpage,
    })
