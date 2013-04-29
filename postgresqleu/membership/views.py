from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect
from django.template import RequestContext
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import transaction

from models import *
from forms import *

from postgresqleu.util.decorators import ssl_required
from postgresqleu.invoices.util import InvoiceManager, InvoicePresentationWrapper
from postgresqleu.invoices.models import InvoiceProcessor

from datetime import date, datetime

@ssl_required
@login_required
@transaction.commit_on_success
def home(request):
	try:
		member = Member.objects.get(user=request.user)
		registration_complete = True

		# We have a batch job that expires members, but do it here as well to make sure
		# the web is up to date with information if necessary.
		if member.paiduntil and member.paiduntil < date.today():
			MemberLog(member=member,
					  timestamp=datetime.now(),
					  message="Membership expired").save()
			member.membersince = None
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
			if request.POST["submit"] == "Generate invoice":
				# Generate an invoice for the user
				if member.activeinvoice:
					raise Exception("This should not happen - generating invoice when one already exists!")
				manager = InvoiceManager()
				processor = InvoiceProcessor.objects.get(processorname="membership processor")
				invoicerows = [('PostgreSQL Europe - 2 years membership - %s' % request.user.email, 1, 10),]
				member.activeinvoice = manager.create_invoice(
					request.user,
					request.user.email,
					request.user.first_name + ' ' + request.user.last_name,
					'', # We don't have an address
					'PostgreSQL Europe membership for %s'% request.user.email,
					datetime.now(),
					datetime.now(),
					invoicerows,
					processor = processor,
					processorid = member.pk,
					)
				member.activeinvoice.save()
				member.save()
				# Invoice info will automatically render on the main form page
	else:
		form = MemberForm(instance=member)

	logdata = MemberLog.objects.filter(member=member).order_by('timestamp')[:30]

	return render_to_response('membership/index.html', {
		'form': form,
		'member': member,
		'invoice': InvoicePresentationWrapper(member.activeinvoice, "%s/membership/" % settings.SITEBASE_SSL),
		'registration_complete': registration_complete,
		'logdata': logdata,
		'amount': 10, # price for two years
	}, context_instance=RequestContext(request))


def userlist(request):
	members = Member.objects.select_related('country').filter(listed=True, paiduntil__gt=datetime.now()).order_by('fullname')
	return render_to_response('community/userlist.html', {
		'members': members,
	}, context_instance=RequestContext(request))
