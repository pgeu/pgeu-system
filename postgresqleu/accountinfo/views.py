from django.http import HttpResponse
from django.db.models import Q
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User


import json

from postgresqleu.util.decorators import user_passes_test_or_error
from postgresqleu.auth import user_search, user_import

@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
def search(request):
	term = request.GET['term']
	upstream = request.GET.get('upstream', False)

	users = User.objects.filter(
		Q(username__icontains=term) |
		Q(first_name__icontains=term) |
		Q(last_name__icontains=term) |
		Q(email__icontains=term)
		)
	if users:
		return HttpResponse(json.dumps([{'ui': u.id, 'u': u.username, 'n': u.first_name + ' ' + u.last_name, 'e': u.email} for u in users]), content_type='application/json')

	if not upstream:
		return HttpResponse('[]', content_type='application/json')

	# Perform upstream search
	users = user_search(term)
	# All users need a negative id so we can differentiate them
	for n in range(0, len(users)):
		users[n]['i'] = -1-n
	return HttpResponse(json.dumps([{'ui': u['i'],
									 'u': u['u'],
									 'n': u['f'] + ' ' + u['l'],
									 'e': u['e'],
									 } for u in users]), content_type='application/json')

@login_required
@user_passes_test_or_error(lambda u: u.has_module_perms('invoices'))
@transaction.atomic
def importuser(request):
	uid = request.POST['uid']
	try:
		user_import(uid)
	except Exception, e:
		return HttpResponse('%s' % e, content_type='text/plain')

	return HttpResponse('OK', content_type='text/plain')
