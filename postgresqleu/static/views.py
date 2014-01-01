from django.http import HttpResponse, Http404
from django.template import TemplateDoesNotExist, loader, Context

# Fallback handler for URLs not matching anything else. Fall them
# back to a static template. If that one is not found, send a 404
# error.
def static_fallback(request, url):
	try:
		# Disallow all URLs that back-step
		if url.find('..') > -1:
			raise TemplateDoesNotExist

		t = loader.get_template('pages/%s.html' % url)
		return HttpResponse(t.render(Context()))

	except TemplateDoesNotExist:
		raise Http404('Page not found')

