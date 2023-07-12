from django.http import HttpResponse, Http404
from django.template import loader, TemplateDoesNotExist

import re

re_staticfilenames = re.compile("^[0-9A-Z/_-]+$", re.IGNORECASE)


# Fallback handler for URLs not matching anything else. Fall them
# back to a static template. If that one is not found, send a 404
# error.
def static_fallback(request, url):
    # Disallow all URLs that back-step
    if url.find('..') > -1:
        raise Http404('Page not found')

    if not re_staticfilenames.match(url):
        raise Http404('Page not found.')

    if len(url) > 250:
        # Maximum length is really per-directory, but we shouldn't have any pages/fallback
        # urls with anywhere *near* that, so let's just limit it on the whole
        raise Http404('Page not found.')

    try:
        t = loader.get_template('pages/%s.html' % url)
        return HttpResponse(t.render())
    except TemplateDoesNotExist:
        raise Http404('Page not found')
