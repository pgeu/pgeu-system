from django.shortcuts import render
from django.http import HttpResponseForbidden, Http404

import codecs
import os
import re
import markdown

from models import Conference
from backendviews import get_authenticated_conference

reTitle = re.compile('<h1>([^<]+)</h1>')

_reSvgInline = re.compile('<img alt="([^"]+)" src="([^"]+)\.svg" />')
def _replaceSvgInline(m):
	# Group 1 = alt text
	# Group 2 = filename excluding svg
	filename = 'docs/confreg/{0}.svg'.format(m.group(2))
	if not os.path.isfile(filename):
		return m.group(0)

	with codecs.open(filename, 'r', 'utf8') as f:
		return f.read()

def docspage(request, urlname, page):
	if urlname:
		conference = get_authenticated_conference(request, urlname.rstrip('/'))
	else:
		# Allow a person who has *any* permissions on a conference to read the docs,
		# because, well, they are docs.
		if not request.user.is_superuser:
			if not Conference.objects.filter(administrators=request.user).exists():
				return HttpResponseForbidden("Access denied")
		conference = None

	if page:
		page = page.rstrip('/')
		urlpage = page
	else:
		page = "index"
		urlpage = ''

	# Do we have the actual docs file?
	# It's safe to just put the filename in here, because the regexp in urls.py ensures
	# that we can not get into a path traversal case.
	filename = 'docs/confreg/{0}.md'.format(page)
	if not os.path.isfile(filename):
		raise Http404()

	with open(filename) as f:
		md = markdown.Markdown(extensions=['markdown.extensions.def_list'])
		contents = md.convert(f.read())
	contents = _reSvgInline.sub(lambda m: _replaceSvgInline(m), contents)

	# Find the title
	m = reTitle.search(contents)
	if m:
		title = m.group(1)
	else:
		title = 'PostgreSQL Europe Conference Administration'

	return render(request, 'confreg/admin_backend_docpage.html', {
		'conference': conference,
		'page': page,
		'contents': contents,
		'title': title,
		'urlpage': urlpage,
	})
