from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect
from django.template import RequestContext
from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings

@login_required
def home(request):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))

	return render_to_response('membership/index.html', {
	}, context_instance=RequestContext(request))

