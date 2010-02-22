from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect
from django.template import RequestContext
from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings

from models import *
from forms import *

from datetime import date, datetime

@login_required
def home(request):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))

	try:
		member = Member.objects.get(user=request.user)
		registration_complete = True

		# We have a batch job that expires members, but do it here as well to make sure
		# the web is up to date with information if necessary.
		if member.paiduntil and member.paiduntil < date.today():
			MemberLog(member=member,
					  timestamp=datetime.now(),
					  message="Membership expired").save()
			member.paiduntil = None
			member.save()

	except Member.DoesNotExist:
		# No record yet, so we create one. Base the information on whatever we
		# have already.
		member = Member(user=request.user, fullname=request.user.first_name)
		registration_complete = False

	if request.method == "POST":
		form = MemberForm(data=request.POST, instance=member)
		if form.is_valid():
			member = form.save(commit=False)
			member.user = request.user
			member.save()
			if not registration_complete:
				MemberLog(member=member,
						  timestamp=datetime.now(),
						  message="Registration received, awaiting payment").save()
				registration_complete = True # So we show the payment info!
			elif form.has_changed():
				# Figure out what changed
				MemberLog(member=member,
						  timestamp=datetime.now(),
						  message="Modified registration data for field(s): %s" % (", ".join(form._changed_data)),
						  ).save()
	else:
		form = MemberForm(instance=member)

	logdata = MemberLog.objects.filter(member=member).order_by('timestamp')[:30]

	return render_to_response('membership/index.html', {
		'form': form,
		'member': member,
		'registration_complete': registration_complete,
		'logdata': logdata,
		'amount': 10, # price for two years
	}, context_instance=RequestContext(request))


def userlist(request):
	members = Member.objects.select_related('country').filter(listed=True, paiduntil__gt=datetime.now()).order_by('fullname')
	return render_to_response('community/userlist.html', {
		'members': members,
	}, context_instance=RequestContext(request))
