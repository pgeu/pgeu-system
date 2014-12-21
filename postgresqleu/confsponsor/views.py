from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.conf import settings
from django.template import RequestContext
from django.contrib import messages
from django.contrib.auth.models import User

from datetime import datetime, timedelta

from postgresqleu.util.decorators import ssl_required

from postgresqleu.invoices.util import InvoiceManager
from postgresqleu.invoices.models import InvoiceProcessor
from postgresqleu.confreg.models import Conference
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.util.storage import InlineEncodedStorage

from models import Sponsor, SponsorshipLevel, SponsorshipBenefit
from models import SponsorClaimedBenefit, SponsorMail
from forms import SponsorSignupForm, SponsorSendEmailForm
from benefits import get_benefit_class

@ssl_required
@login_required
def sponsor_dashboard(request):
	currentsponsors = Sponsor.objects.filter(managers=request.user, conference__enddate__gte=datetime.today()).order_by('conference__startdate')
	pastsponsors = Sponsor.objects.filter(managers=request.user, conference__enddate__lt=datetime.today()).order_by('conference__startdate')
	conferences = Conference.objects.filter(callforsponsorsopen=True)

	return render_to_response('confsponsor/dashboard.html', {
		"currentsponsors": currentsponsors,
		"pastsponsors": pastsponsors,
		"conferences": conferences,
		})

@ssl_required
@login_required
def sponsor_conference(request, sponsorid):
	sponsor = get_object_or_404(Sponsor, id=sponsorid, managers=request.user)
	unclaimedbenefits = SponsorshipBenefit.objects.filter(level=sponsor.level, benefit_class__isnull=False).exclude(sponsorclaimedbenefit__sponsor=sponsor)
	claimedbenefits = SponsorClaimedBenefit.objects.filter(sponsor=sponsor).order_by('confirmed', 'benefit__sortkey')
	noclaimbenefits = SponsorshipBenefit.objects.filter(level=sponsor.level, benefit_class__isnull=True)
	mails = SponsorMail.objects.filter(conference=sponsor.conference, levels=sponsor.level)

	for b in claimedbenefits:
		if b.benefit.benefit_class and not b.declined:
			b.claimhtml = get_benefit_class(b.benefit.benefit_class)(sponsor.level, b.benefit.class_parameters).render_claimdata(b)

	return render_to_response('confsponsor/sponsor.html', {
		'sponsor': sponsor,
		'unclaimedbenefits': unclaimedbenefits,
		'claimedbenefits': claimedbenefits,
		'noclaimbenefits': noclaimbenefits,
		'mails': mails,
		}, RequestContext(request))

@ssl_required
@login_required
def sponsor_manager_delete(request, sponsorid):
	sponsor = get_object_or_404(Sponsor, id=sponsorid, managers=request.user, confirmed=True)
	user = get_object_or_404(User, id=request.GET['id'])

	if user == request.user:
		messages.warning(request, "Can't delete yourself! Have one of your colleagues do it...")
		return HttpResponseRedirect('../../')

	sponsor.managers.remove(user)
	sponsor.save()
	messages.info(request, "User %s removed as manager." % user.username)
	return HttpResponseRedirect('../../')

@ssl_required
@login_required
def sponsor_manager_add(request, sponsorid):
	sponsor = get_object_or_404(Sponsor, id=sponsorid, managers=request.user, confirmed=True)

	if not request.POST['email']:
		messages.warning(request, "Email not specified")
		return HttpResponseRedirect('../../')
	try:
		user = User.objects.get(email=request.POST['email'])
		sponsor.managers.add(user)
		sponsor.save()
		messages.info(request, "User %s added as manager." % user.username)
		return HttpResponseRedirect('../../')
	except User.DoesNotExist:
		messages.warning(request, "Could not find user with email address %s" % request.POST['email'])
		return HttpResponseRedirect('../../')

@ssl_required
@login_required
def sponsor_view_mail(request, sponsorid, mailid):
	sponsor = get_object_or_404(Sponsor, id=sponsorid, managers=request.user, confirmed=True)
	mail = get_object_or_404(SponsorMail, conference=sponsor.conference, levels=sponsor.level, id=mailid)

	return render_to_response('confsponsor/sent_mail.html', {
		'conference': sponsor.conference,
		'mail': mail,
		}, RequestContext(request))

@ssl_required
@login_required
def sponsor_signup_dashboard(request, confurlname):
	conference = get_object_or_404(Conference, urlname=confurlname, callforsponsorsopen=True)

	current_signups = Sponsor.objects.filter(managers=request.user, conference=conference)
	levels = SponsorshipLevel.objects.filter(conference=conference)

	return render_to_response('confsponsor/signup.html', {
		'conference': conference,
		'levels': levels,
		'current': current_signups,
		})

@ssl_required
@login_required
@transaction.commit_on_success
def sponsor_signup(request, confurlname, levelurlname):
	conference = get_object_or_404(Conference, urlname=confurlname, callforsponsorsopen=True)
	level = get_object_or_404(SponsorshipLevel, conference=conference, urlname=levelurlname)

	user_name = request.user.first_name + ' ' + request.user.last_name

	if request.method == 'POST':
		form = SponsorSignupForm(conference, data=request.POST)
		if form.is_valid():
			# Create a new sponsorship record always
			sponsor = Sponsor(conference=conference,
							  name=form.cleaned_data['name'],
							  level=level)
			sponsor.save()
			sponsor.managers.add(request.user)
			sponsor.save()

			if level.instantbuy:
				# Create the invoice, so it can be paid right away!
				invoicerows = [
					['%s %s sponsorship' % (conference, level), 1, level.levelcost],
				]
				manager = InvoiceManager()
				processor = InvoiceProcessor.objects.get(processorname="confsponsor processor")
				sponsor.invoice = manager.create_invoice(
					request.user,
					request.user.email,
					user_name,
					'%s\n%s' % (form.cleaned_data['name'], form.cleaned_data['address']),
					'%s sponsorship' % conference.conferencename,
					datetime.now(),
					datetime.now() + timedelta(days=30),
					invoicerows,
					processor = processor,
					processorid = sponsor.pk,
					bankinfo = True,
					accounting_account = settings.ACCOUNTING_CONFSPONSOR_ACCOUNT,
					accounting_object = conference.accounting_object,
				)
				sponsor.invoice.save()
				sponsor.save()

			# Redirect back to edit the actual sponsorship entry
			return HttpResponseRedirect('/events/sponsor/%s/' % sponsor.id)
	else:
		form = SponsorSignupForm(conference)

	return render_to_response('confsponsor/signupform.html', {
		'user_name': user_name,
		'conference': conference,
		'level': level,
		'form': form,
		})

@ssl_required
@login_required
@transaction.commit_on_success
def sponsor_claim_benefit(request, sponsorid, benefitid):
	sponsor = get_object_or_404(Sponsor, id=sponsorid, managers=request.user)
	benefit = get_object_or_404(SponsorshipBenefit, id=benefitid, level=sponsor.level)

	if not sponsor.confirmed:
		# Should not happen
		return HttpResponseRedirect("/events/sponsor/%s/" % sponsor.id)

	if not benefit.benefit_class:
		messages.warning(request, "Benefit does not require claiming")
		return HttpResponseRedirect("/events/sponsor/%s/" % sponsor.id)

	# Let's see if it's already claimed
	if SponsorClaimedBenefit.objects.filter(sponsor=sponsor, benefit=benefit).exists():
		messages.warning(request, "Benefit has already been claimed")
		return HttpResponseRedirect("/events/sponsor/%s/" % sponsor.id)

	# Find the actual type of benefit this is, so we know what to do about it
	benefitclass = get_benefit_class(benefit.benefit_class)(benefit.level, benefit.class_parameters)

	formclass = benefitclass.generate_form()

	# Are we trying to process incoming data yet?
	if request.method == 'POST':
		form = formclass(benefit, request.POST, request.FILES)
		if form.is_valid():
			# Always create a new claim here - we might support editing an existing one
			# sometime in the future, but not yet...
			claim = SponsorClaimedBenefit(sponsor=sponsor, benefit=benefit, claimedat=datetime.now(), claimedby=request.user)
			claim.save() # generate an id

			send_mail = benefitclass.save_form(form, claim, request)

			claim.save() # Just in case the claimdata field was modified

			if send_mail:
				if claim.declined:
					mailstr = "Sponsor %s for conference %s has declined benefit %s.\n" % (sponsor, sponsor.conference, benefit)
				elif claim.confirmed:
					# Auto-confirmed, so nothing to do here
					mailstr = "Sponsor %s for conference %s has claimed benefit %s.\n\nThis has been automatically processed, so there is nothing more to do.\n" % (sponsor, sponsor.conference, benefit)
				else:
					mailstr = "Sponsor %s for conference %s has claimed benefit %s\n\nThis benefit requires confirmation (and possibly some\nmore actions before that). Please go to\n%s/events/sponsor/admin/%s/\nand approve as necessary!" % (
						sponsor,
						sponsor.conference,
						benefit,
						settings.SITEBASE_SSL,
						sponsor.conference.urlname)
				send_simple_mail(sponsor.conference.sponsoraddr,
								 sponsor.conference.sponsoraddr,
								 "Sponsor %s %s sponsorship benefit %s" % (sponsor, claim.declined and 'declined' or 'claimed', benefit),
								 mailstr,
								 )


			messages.info(request, "Benefit \"%s\" has been %s." % (benefit, claim.declined and 'declined' or 'claimed'))
			return HttpResponseRedirect("/events/sponsor/%s/" % sponsor.id)
	else:
		form = formclass(benefit)

	return render_to_response('confsponsor/claim_form.html', {
		'conference': sponsor.conference,
		'sponsor': sponsor,
		'benefit': benefit,
		'form': form,
		}, RequestContext(request))


@ssl_required
@login_required
def sponsor_admin_dashboard(request, confurlname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confurlname)
	else:
		conference = get_object_or_404(Conference, urlname=confurlname, admin=request.user)

	confirmed_sponsors = Sponsor.objects.filter(conference=conference, confirmed=True).order_by('-level__levelcost', 'confirmedat')
	unconfirmed_sponsors = Sponsor.objects.filter(conference=conference, confirmed=False).order_by('level__levelcost', 'name')

	unconfirmed_benefits = SponsorClaimedBenefit.objects.filter(sponsor__conference=conference, confirmed=False).order_by('sponsor__level__levelcost', 'sponsor', 'benefit__sortkey')

	mails = SponsorMail.objects.filter(conference=conference)

	return render_to_response('confsponsor/admin_dashboard.html', {
		'conference': conference,
		'confirmed_sponsors': confirmed_sponsors,
		'unconfirmed_sponsors': unconfirmed_sponsors,
		'unconfirmed_benefits': unconfirmed_benefits,
		'mails': mails,
		}, RequestContext(request))

@ssl_required
@login_required
def sponsor_admin_sponsor(request, confurlname, sponsorid):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confurlname)
	else:
		conference = get_object_or_404(Conference, urlname=confurlname, admin=request.user)

	sponsor = get_object_or_404(Sponsor, id=sponsorid, conference=conference)

	if request.method == 'POST' and request.POST['confirm'] == '1':
		# Confirm one of the benefits, so do this before we load the list
		benefit = get_object_or_404(SponsorClaimedBenefit, sponsor=sponsor, id=request.POST['claimid'])
		benefit.confirmed = True
		benefit.save()
		return HttpResponseRedirect('.')

	unclaimedbenefits = SponsorshipBenefit.objects.filter(level=sponsor.level, benefit_class__isnull=False).exclude(sponsorclaimedbenefit__sponsor=sponsor)
	claimedbenefits = SponsorClaimedBenefit.objects.filter(sponsor=sponsor).order_by('confirmed', 'benefit__sortkey')
	noclaimbenefits = SponsorshipBenefit.objects.filter(level=sponsor.level, benefit_class__isnull=True)

	for b in claimedbenefits:
		if b.benefit.benefit_class:
			b.claimhtml = get_benefit_class(b.benefit.benefit_class)(sponsor.level, b.benefit.class_parameters).render_claimdata(b)


	return render_to_response('confsponsor/admin_sponsor.html', {
		'conference': conference,
		'sponsor': sponsor,
		'claimedbenefits': claimedbenefits,
		'unclaimedbenefits': unclaimedbenefits,
		'noclaimbenefits': noclaimbenefits,
		}, RequestContext(request))

@ssl_required
@login_required
def sponsor_admin_benefit(request, confurlname, benefitid):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confurlname)
	else:
		conference = get_object_or_404(Conference, urlname=confurlname, admin=request.user)

	benefit = get_object_or_404(SponsorClaimedBenefit, id=benefitid, sponsor__conference=conference)
	if benefit.benefit.benefit_class:
		claimdata = get_benefit_class(benefit.benefit.benefit_class)(benefit.benefit.level, benefit.benefit.class_parameters).render_claimdata(benefit)
	else:
		claimdata = None

	if request.method == 'POST' and request.POST['confirm'] == '1':
		# Confirm this benefit!
		benefit.confirmed = True
		benefit.save()
		return HttpResponseRedirect('.')


	return render_to_response('confsponsor/admin_benefit.html', {
		'conference': conference,
		'sponsor': benefit.sponsor,
		'benefit': benefit,
		'claimdata': claimdata,
		}, RequestContext(request))

@ssl_required
@login_required
@transaction.commit_on_success
def sponsor_admin_send_mail(request, confurlname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confurlname)
	else:
		conference = get_object_or_404(Conference, urlname=confurlname, admin=request.user)

	if request.method == 'POST':
		form = SponsorSendEmailForm(conference, data=request.POST)
		if form.is_valid():
			# Create a message record
			msg = SponsorMail(conference=conference,
							  subject=form.data['subject'],
							  message=form.data['message'])
			msg.save()
			for l in form.data.getlist('levels'):
				msg.levels.add(l)
			msg.save()

			# Now also send the email out to the *current* subscribers
			sponsors = Sponsor.objects.filter(conference=conference, level__in=form.data.getlist('levels'), confirmed=True)
			recipients = []
			for sponsor in sponsors:
				for manager in sponsor.managers.all():
					recipients.append(manager.email)
			recipients = set(recipients)
			for r in recipients:
				send_simple_mail(conference.sponsoraddr, r, msg.subject, msg.message)

			messages.info(request, "Email sent to %s recipients, and added to all sponsor pages" % len(recipients))
			return HttpResponseRedirect("../")
	else:
		form = SponsorSendEmailForm(conference)

	return render_to_response('confsponsor/sendmail.html', {
		'conference': conference,
		'form': form,
	}, RequestContext(request))

@ssl_required
@login_required
def sponsor_admin_view_mail(request, confurlname, mailid):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confurlname)
	else:
		conference = get_object_or_404(Conference, urlname=confurlname, admin=request.user)

	mail = get_object_or_404(SponsorMail, conference=conference, id=mailid)
	return render_to_response('confsponsor/sent_mail.html', {
		'conference': conference,
		'mail': mail,
		'admin': True,
		}, RequestContext(request))

@ssl_required
@login_required
def sponsor_admin_imageview(request, benefitid):
	# Image is fetched as part of a benefit, so find the benefit

	benefit = get_object_or_404(SponsorClaimedBenefit, id=benefitid)
	if not request.user.is_superuser:
		# Check permissions for non superusers
		if not benefit.sponsor.conference == request.user:
			return HttpResponseForbidden("Access denied")

	# If the benefit existed, we have verified the permissions, so we can now show
	# the image itself.
	storage = InlineEncodedStorage('benefit_image')
	f = storage.open(str(benefit.id))

	# XXX: do we need to support non-png at some point? store info in claimdata!
	resp = HttpResponse(content_type='image/png')
	resp.write(f.read())
	return resp
