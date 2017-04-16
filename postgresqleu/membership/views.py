from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
from django.template import RequestContext
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.db import transaction
from django.db.models import Q

from models import Member, MemberLog, Meeting, MemberMeetingKey
from forms import MemberForm

from postgresqleu.util.decorators import user_passes_test_or_error
from postgresqleu.invoices.util import InvoiceManager, InvoicePresentationWrapper
from postgresqleu.invoices.models import InvoiceProcessor
from postgresqleu.confreg.forms import EmailSendForm
from postgresqleu.mailqueue.util import send_simple_mail

from datetime import date, datetime, timedelta
import json
import base64
import os

@login_required
@transaction.atomic
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
				invoicerows = [('%s - 2 years membership - %s' % (settings.ORG_NAME, request.user.email), 1, 10, None),]
				member.activeinvoice = manager.create_invoice(
					request.user,
					request.user.email,
					request.user.first_name + ' ' + request.user.last_name,
					'', # We don't have an address
					'%s membership for %s' % (settings.ORG_NAME, request.user.email),
					datetime.now(),
					datetime.now(),
					invoicerows,
					processor = processor,
					processorid = member.pk,
					bankinfo = False,
					canceltime = datetime.now() + timedelta(days=7),
					accounting_account = settings.ACCOUNTING_MEMBERSHIP_ACCOUNT
					)
				member.activeinvoice.save()
				member.save()

				# We'll redirect back to the same page, so make sure
				# someone doing say a hard refresh on the page doesn't
				# cause weird things to happen.
				return HttpResponseRedirect('/membership/')
	else:
		form = MemberForm(instance=member)

	logdata = MemberLog.objects.filter(member=member).order_by('-timestamp')[:30]

	return render_to_response('membership/index.html', {
		'form': form,
		'member': member,
		'invoice': InvoicePresentationWrapper(member.activeinvoice, "%s/membership/" % settings.SITEBASE),
		'registration_complete': registration_complete,
		'logdata': logdata,
		'amount': 10, # price for two years
	}, context_instance=RequestContext(request))


def userlist(request):
	members = Member.objects.select_related('country').filter(listed=True, paiduntil__gt=datetime.now()).order_by('fullname')
	return render_to_response('community/userlist.html', {
		'members': members,
	}, context_instance=RequestContext(request))


# Admin view that's used to send email to multiple users
@login_required
@user_passes_test_or_error(lambda u: u.is_superuser)
@transaction.atomic
def admin_email(request):
	if request.method == 'POST':
		form = EmailSendForm(data=request.POST)
		if form.is_valid():
			# Ok, actually send the email. This is the scary part!
			ids = form.data['ids'].split(',')
			members = Member.objects.filter(pk__in=ids)
			emails = [r.user.email for r in members]
			for e in emails:
				send_simple_mail(form.data['sender'], e, form.data['subject'], form.data['text'])

			messages.info(request, 'Sent email to %s recipients' % len(emails))
			return HttpResponseRedirect('/admin/membership/member/?' + form.data['returnurl'])
		else:
			ids = form.data['ids'].split(',')
	else:
		ids = request.GET['ids']
		form = EmailSendForm(initial={'ids': ids, 'returnurl': request.GET['orig']})
		ids = ids.split(',')

	recipients = [m.user.email for m in Member.objects.filter(pk__in=ids)]
	return render_to_response('membership/admin_email.html', {
		'form': form,
		'recipientlist': ', '.join(recipients),
		}, RequestContext(request))

@login_required
def meetings(request):
	# Only available for actual members
	member = get_object_or_404(Member, user=request.user)
	q = Q(dateandtime__gte=datetime.now()-timedelta(hours=4)) & (Q(allmembers=True) | Q(members=member))
	meetings = Meeting.objects.filter(q).order_by('dateandtime')

	return render_to_response('membership/meetings.html', {
		'active': member.paiduntil and member.paiduntil >= datetime.today().date(),
		'member': member,
		'meetings': meetings,
		})

@login_required
@transaction.atomic
def meeting(request, meetingid):
	# View a single meeting
	meeting = get_object_or_404(Meeting, pk=meetingid)
	member = get_object_or_404(Member, user=request.user)

	if not (member.paiduntil and member.paiduntil >= datetime.today().date()):
		return HttpResponse("Your membership is not active")

	if not meeting.allmembers:
		if not meeting.members.filter(pk=member.pk).exists():
			return HttpResponse("Access denied.")

	# Allow four hours in the past, just in case
	if meeting.dateandtime + timedelta(hours=4) < datetime.now():
		return HttpResponse("Meeting is in the past.")

	if member.paiduntil < meeting.dateandtime.date():
		return HttpResponse("Your membership expires before the meeting")

	if not meeting.joining_active:
		return HttpResponse("This meeting is not open for joining yet")

	# All is well with this member. Generate a key if necessary
	(key, created) = MemberMeetingKey.objects.get_or_create(member=member, meeting=meeting)
	if created:
		# New key!
		key.key = base64.urlsafe_b64encode(os.urandom(40)).rstrip('=')
		key.save()

	return render_to_response('membership/meeting.html', {
		'member': member,
		'meeting': meeting,
		'key': key,
		})

# API calls from meeting bot
def meetingcode(request):
	secret = request.GET['s']
	meetingid = request.GET['m']

	try:
		key = MemberMeetingKey.objects.get(key=secret, meeting__pk=meetingid)
		member = key.member
	except MemberMeetingKey.DoesNotExist:
		return HttpResponse(json.dumps({'err': 'Authentication key not found. Please see %s/membership/meetings/ to get your correct key!' % settings.SITEBASE}),
							content_type='application/json')

	# Return a JSON object with information about the member
	return HttpResponse(json.dumps({'username': member.user.username,
										  'email': member.user.email,
										  'name': member.fullname,
									  }), content_type='application/json')
