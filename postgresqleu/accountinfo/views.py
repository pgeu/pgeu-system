from django.http import HttpResponse
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User


import simplejson as json

from postgresqleu.util.decorators import user_passes_test_or_error, ssl_required

@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def search(request):
	term = request.GET['term']

	users = User.objects.filter(
		Q(username__icontains=term) |
		Q(first_name__icontains=term) |
		Q(last_name__icontains=term) |
		Q(email__icontains=term)
		)
	return HttpResponse(json.dumps([{'ui': u.id, 'u': u.username, 'n': u.first_name + ' ' + u.last_name, 'e': u.email} for u in users]), content_type='application/json')
