from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden, Http404
from django.contrib.auth.decorators import login_required
from django.db import transaction, connection
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import User

from datetime import datetime, timedelta

from postgresqleu.auth import user_search, user_import

from postgresqleu.confreg.models import Conference, PrepaidVoucher, DiscountCode
from postgresqleu.mailqueue.util import send_simple_mail
from postgresqleu.util.storage import InlineEncodedStorage
from postgresqleu.util.decorators import user_passes_test_or_error
from postgresqleu.invoices.util import InvoiceWrapper

from models import Sponsor, SponsorshipLevel, SponsorshipBenefit
from models import SponsorClaimedBenefit, SponsorMail, SponsorshipContract
from models import PurchasedVoucher
from forms import SponsorSignupForm, SponsorSendEmailForm
from forms import PurchaseVouchersForm, PurchaseDiscountForm
from forms import AdminCopySponsorshipLevelForm
from benefits import get_benefit_class
from invoicehandler import create_sponsor_invoice, confirm_sponsor
from invoicehandler import create_voucher_invoice
from vatutil import validate_eu_vat_number

@login_required
def sponsor_dashboard(request):
	# We define "past sponsors" as those older than a month - because we have to pick something.
	currentsponsors = Sponsor.objects.filter(managers=request.user, conference__enddate__gte=datetime.today()-timedelta(days=31)).order_by('conference__startdate')
	pastsponsors = Sponsor.objects.filter(managers=request.user, conference__enddate__lt=datetime.today()-timedelta(days=31)).order_by('conference__startdate')
	conferences = Conference.objects.filter(callforsponsorsopen=True, startdate__gt=datetime.today()).order_by('startdate')

	return render(request, 'confsponsor/dashboard.html', {
		"currentsponsors": currentsponsors,
		"pastsponsors": pastsponsors,
		"conferences": conferences,
		})

def _get_sponsor_and_admin(sponsorid, request, onlyconfirmed=True):
	if not onlyconfirmed:
		sponsor = get_object_or_404(Sponsor, id=sponsorid)
	else:
		sponsor = get_object_or_404(Sponsor, id=sponsorid, confirmed=True)
	if not sponsor.managers.filter(pk=request.user.id).exists():
		if not sponsor.conference.administrators.filter(pk=request.user.id):
			# XXX: Can only raise 404 for now, should have custom middleware to make this nicer
			raise Http404("Access denied")
		return sponsor, True
	else:
		return sponsor, False

@login_required
def sponsor_conference(request, sponsorid):
	sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request, False)

	unclaimedbenefits = SponsorshipBenefit.objects.filter(level=sponsor.level, benefit_class__isnull=False).exclude(sponsorclaimedbenefit__sponsor=sponsor)
	claimedbenefits = SponsorClaimedBenefit.objects.filter(sponsor=sponsor).order_by('confirmed', 'benefit__sortkey')
	noclaimbenefits = SponsorshipBenefit.objects.filter(level=sponsor.level, benefit_class__isnull=True)
	mails = SponsorMail.objects.filter(conference=sponsor.conference, levels=sponsor.level)
	vouchers = PrepaidVoucher.objects.filter(batch__sponsor=sponsor)
	pendingvouchers = PurchasedVoucher.objects.filter(sponsor=sponsor, batch__isnull=True)
	discountcodes = DiscountCode.objects.filter(sponsor=sponsor)

	for b in claimedbenefits:
		if b.benefit.benefit_class and not b.declined:
			b.claimhtml = get_benefit_class(b.benefit.benefit_class)(sponsor.level, b.benefit.class_parameters).render_claimdata(b)

	return render(request, 'confsponsor/sponsor.html', {
		'conference': sponsor.conference,
		'sponsor': sponsor,
		'unclaimedbenefits': unclaimedbenefits,
		'claimedbenefits': claimedbenefits,
		'noclaimbenefits': noclaimbenefits,
		'mails': mails,
		'vouchers': vouchers,
		'pendingvouchers': pendingvouchers,
		'discountcodes': discountcodes,
		'is_admin': is_admin,
		})

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

@login_required
@transaction.atomic
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
		# Try an upstream search if the user is not here
		users = user_search(request.POST['email'])
		if len(users) == 1 and users[0]['e'] == request.POST['email']:
			try:
				user_import(users[0]['u'])
				try:
					u = User.objects.get(username=users[0]['u'])
					sponsor.managers.add(u)
					sponsor.save()
					messages.info(request, "User with email %s imported as user %s." % (u.email, u.username))
					messages.info(request, "User %s added as manager." % u.username)
				except User.DoesNotExist:
					messages.warning(request, "Failed to re-find user %s after import" % users[0]['u'])
			except Exception, e:
				messages.warning(request, "Failed to import user with email %s (userid %s): %s" % (users[0]['e'], users[0]['u'], e))
		else:
			messages.warning(request, "Could not find user with email address %s" % request.POST['email'])
		return HttpResponseRedirect('../../')

@login_required
def sponsor_view_mail(request, sponsorid, mailid):
	sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request)

	mail = get_object_or_404(SponsorMail, conference=sponsor.conference, levels=sponsor.level, id=mailid)

	return render(request, 'confsponsor/sent_mail.html', {
		'conference': sponsor.conference,
		'mail': mail,
		})

@login_required
@transaction.atomic
def sponsor_purchase_voucher(request, sponsorid):
	sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request)
	conference = sponsor.conference

	if request.method == 'POST':
		form = PurchaseVouchersForm(conference, data=request.POST)
		if form.is_valid():
			# Create an invoice (backwards order?)
			rt = form.cleaned_data['regtype']
			invoice = create_voucher_invoice(sponsor,
											 request.user,
											 rt,
											 int(form.cleaned_data['num']))

			# Create a purchase order
			pv = PurchasedVoucher(sponsor=sponsor,
								  user=request.user,
								  regtype=form.cleaned_data['regtype'],
								  num=int(form.cleaned_data['num']),
								  invoice=invoice)
			pv.save()
			invoice.processorid = pv.pk
			invoice.save()

			wrapper = InvoiceWrapper(invoice)
			wrapper.email_invoice()

			return HttpResponseRedirect('/invoices/{0}/'.format(invoice.pk))
	else:
		form = PurchaseVouchersForm(conference)

	return render(request, 'confsponsor/purchasevouchers.html', {
		'conference': conference,
		'user_name': request.user.first_name + ' ' + request.user.last_name,
		'sponsor': sponsor,
		'form': form,
		})

@login_required
@transaction.atomic
def sponsor_purchase_discount(request, sponsorid):
	sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request)
	conference = sponsor.conference

	if request.method == 'POST':
		if request.POST.has_key('confirm'):
			form = PurchaseDiscountForm(conference, showconfirm=True, data=request.POST)
		else:
			form = PurchaseDiscountForm(conference, data=request.POST)
		if form.is_valid():
			if not form.cleaned_data.has_key('confirm'):
				form = PurchaseDiscountForm(conference, showconfirm=True, data=request.POST)
			else:
				# Generate the code. We can't generate the invoice at this point, as it
				# will be depending on the discount code.
				code = DiscountCode(conference=conference,
									code=form.cleaned_data['code'],
									discountamount=form.cleaned_data['amount'],
									discountpercentage=form.cleaned_data['percent'],
									regonly=True,
									validuntil=form.cleaned_data['expires'],
									maxuses=form.cleaned_data['maxuses'],
									sponsor=sponsor,
									sponsor_rep=request.user,
									is_invoiced=False
									)
				code.save()
				# ManyToMany requires us to save before we can add the required options
				for o in form.cleaned_data['requiredoptions']:
					code.requiresoption.add(o)
				code.save()

				messages.info(request, 'Discount code {0} has been created.'.format(code.code))
				return HttpResponseRedirect('../../')
	else:
		form = PurchaseDiscountForm(conference)

	return render(request, 'confsponsor/purchasediscount.html', {
		'conference': conference,
		'user_name': request.user.first_name + ' ' + request.user.last_name,
		'sponsor': sponsor,
		'form': form,
		})

@login_required
def sponsor_signup_dashboard(request, confurlname):
	conference = get_object_or_404(Conference, urlname=confurlname)
	if not conference.callforsponsorsopen:
		# This one is not open. But if we're an admin, we may bypass
		if not conference.administrators.filter(pk=request.user.id).exists():
			raise Http404()

	current_signups = Sponsor.objects.filter(managers=request.user, conference=conference)
	levels = SponsorshipLevel.objects.filter(conference=conference)

	return render(request, 'confsponsor/signup.html', {
		'conference': conference,
		'levels': levels,
		'current': current_signups,
		})

@login_required
@transaction.atomic
def sponsor_signup(request, confurlname, levelurlname):
	conference = get_object_or_404(Conference, urlname=confurlname)
	if not conference.callforsponsorsopen:
		# This one is not open. But if we're an admin, we may bypass
		if not conference.administrators.filter(pk=request.user.id).exists():
			raise Http404()

	level = get_object_or_404(SponsorshipLevel, conference=conference, urlname=levelurlname, available=True)

	user_name = request.user.first_name + ' ' + request.user.last_name

	if request.method == 'POST':
		form = SponsorSignupForm(conference, data=request.POST)
		if form.is_valid():
			# Create a new sponsorship record always
			sponsor = Sponsor(conference=conference,
							  signupat=datetime.now(),
							  name=form.cleaned_data['name'],
							  displayname=form.cleaned_data['displayname'],
							  url=form.cleaned_data['url'],
							  level=level,
							  twittername = form.cleaned_data.get('twittername', ''),
							  invoiceaddr = form.cleaned_data['address'])
			if settings.EU_VAT:
				sponsor.vatstatus = int(form.cleaned_data['vatstatus'])
				sponsor.vatnumber = form.cleaned_data['vatnumber']
			sponsor.save()
			sponsor.managers.add(request.user)
			sponsor.save()

			mailstr = "Sponsor %s signed up for conference\n%s at level %s.\n\n" % (sponsor.name, conference, level.levelname)

			if level.instantbuy:
				# Create the invoice, so it can be paid right away!
				sponsor.invoice = create_sponsor_invoice(request.user, sponsor)
				sponsor.invoice.save()
				sponsor.save()
				mailstr += "An invoice (#%s) has automatically been generated\nand is awaiting payment." % sponsor.invoice.pk
			else:
				mailstr += "No invoice has been generated as for this level\na signed contract is required first. The sponsor\nhas been instructed to sign and send the contract."

			send_simple_mail(conference.sponsoraddr,
							 conference.sponsoraddr,
							 "Sponsor %s signed up for %s" % (sponsor.name, conference),
							 mailstr,
							 sendername=conference.conferencename)
			# Redirect back to edit the actual sponsorship entry
			return HttpResponseRedirect('/events/sponsor/%s/' % sponsor.id)
	else:
		form = SponsorSignupForm(conference)

	return render(request, 'confsponsor/signupform.html', {
		'user_name': user_name,
		'conference': conference,
		'level': level,
		'form': form,
		})

@login_required
@transaction.atomic
def sponsor_claim_benefit(request, sponsorid, benefitid):
	sponsor, is_admin = _get_sponsor_and_admin(sponsorid, request)
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
					mailstr = u"Sponsor %s for conference %s has declined benefit %s.\n" % (sponsor, sponsor.conference, benefit)
				elif claim.confirmed:
					# Auto-confirmed, so nothing to do here
					mailstr = u"Sponsor %s for conference %s has claimed benefit %s.\n\nThis has been automatically processed, so there is nothing more to do.\n" % (sponsor, sponsor.conference, benefit)
				else:
					mailstr = u"Sponsor %s for conference %s has claimed benefit %s\n\nThis benefit requires confirmation (and possibly some\nmore actions before that). Please go to\n%s/events/sponsor/admin/%s/\nand approve as necessary!" % (
						sponsor,
						sponsor.conference,
						benefit,
						settings.SITEBASE,
						sponsor.conference.urlname)
				send_simple_mail(sponsor.conference.sponsoraddr,
								 sponsor.conference.sponsoraddr,
								 "Sponsor %s %s sponsorship benefit %s" % (sponsor, claim.declined and 'declined' or 'claimed', benefit),
								 mailstr,
								 sendername=sponsor.conference.conferencename,
								 )


			messages.info(request, "Benefit \"%s\" has been %s." % (benefit, claim.declined and 'declined' or 'claimed'))
			return HttpResponseRedirect("/events/sponsor/%s/" % sponsor.id)
	else:
		form = formclass(benefit)

	return render(request, 'confsponsor/claim_form.html', {
		'conference': sponsor.conference,
		'sponsor': sponsor,
		'benefit': benefit,
		'form': form,
		})


@login_required
def sponsor_contract(request, contractid):
	# Our contracts are not secret, are they? Anybody can view them, we just require a login
	# to keep the load down and to make sure they are not spidered.

	contract = get_object_or_404(SponsorshipContract, pk=contractid)

	resp = HttpResponse(content_type='application/pdf')
	resp['Content-disposition'] = 'attachment; filename="%s.pdf"' % contract.contractname
	resp.write(contract.contractpdf.read())
	return resp

@login_required
def sponsor_admin_dashboard(request, confurlname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confurlname)
	else:
		conference = get_object_or_404(Conference, urlname=confurlname, administrators=request.user)

	confirmed_sponsors = Sponsor.objects.filter(conference=conference, confirmed=True).order_by('-level__levelcost', 'confirmedat')
	unconfirmed_sponsors = Sponsor.objects.filter(conference=conference, confirmed=False).order_by('level__levelcost', 'name')

	unconfirmed_benefits = SponsorClaimedBenefit.objects.filter(sponsor__conference=conference, confirmed=False).order_by('sponsor__level__levelcost', 'sponsor', 'benefit__sortkey')

	mails = SponsorMail.objects.filter(conference=conference)

	# Maybe we could do this with the ORM based on data we already have, but SQL is easier
	curs = connection.cursor()
	curs.execute("""
SELECT l.levelname, s.name, b.benefitname,
       CASE WHEN scb.declined='t' THEN 1 WHEN scb.confirmed='f' THEN 2 WHEN scb.confirmed='t' THEN 3 ELSE 0 END AS status
FROM confsponsor_sponsor s
INNER JOIN confsponsor_sponsorshiplevel l ON s.level_id=l.id
INNER JOIN confsponsor_sponsorshipbenefit b ON b.level_id=l.id
LEFT JOIN confsponsor_sponsorclaimedbenefit scb ON scb.sponsor_id=s.id AND scb.benefit_id=b.id
WHERE b.benefit_class IS NOT NULL AND s.confirmed AND s.conference_id=%(confid)s
ORDER BY l.levelcost, l.levelname, s.name, b.sortkey, b.benefitname""", {'confid': conference.id})
	benefitmatrix = {}
	currentlevel = None

	benefitcols = []
	currentmatrix = []
	lastsponsor = None
	currentsponsor = []
	firstsponsor = True
	for levelname, sponsor, benefitname, status in curs.fetchall():
		if lastsponsor != sponsor:
			# New sponsor...
			if currentsponsor:
				# We collected some data, so store it
				currentmatrix.append(currentsponsor)
				firstsponsor = False
			currentsponsor = [sponsor, ]
			lastsponsor = sponsor
		if levelname != currentlevel:
			if currentlevel:
				benefitmatrix[currentlevel] = {
					'matrix': currentmatrix,
					'cols': benefitcols,
				}
				benefitcols = []
				currentmatrix = []
				lastsponsor = sponsor
				currentsponsor = [sponsor, ]
				firstsponsor = True
			currentlevel = levelname
		if firstsponsor:
			benefitcols.append(benefitname)
		currentsponsor.append(status)
	currentmatrix.append(currentsponsor)
	benefitmatrix[currentlevel] = {
		'matrix': currentmatrix,
		'cols': benefitcols,
	}

	return render(request, 'confsponsor/admin_dashboard.html', {
		'conference': conference,
		'confirmed_sponsors': confirmed_sponsors,
		'unconfirmed_sponsors': unconfirmed_sponsors,
		'unconfirmed_benefits': unconfirmed_benefits,
		'mails': mails,
		'benefitcols': benefitcols,
		'benefitmatrix': benefitmatrix,
		})

def _confirm_benefit(request, benefit):
	with transaction.atomic():
		benefit.confirmed = True
		benefit.save()

		messages.info(request, u"Benefit {0} for {1} confirmed.".format(benefit.benefit, benefit.sponsor))

		conference = benefit.sponsor.conference

		# Send email
		for manager in benefit.sponsor.managers.all():
			send_simple_mail(conference.sponsoraddr,
							 manager.email,
							 u"[{0}] sponsorship benefit confirmed".format(conference.conferencename, benefit.benefit),
							 u"Your sponsorship benefit {0} at {1} has been marked as confirmed by the organizers.".format(benefit.benefit, conference.conferencename),
							 sendername=conference.conferencename,
							 receivername=u'{0} {1}'.format(manager.first_name, manager.last_name))
		send_simple_mail(conference.sponsoraddr,
						 conference.sponsoraddr,
						 u"Sponsorship benefit {0} for {1} has been confirmed".format(benefit.benefit, benefit.sponsor),
						 u"Sponsorship benefit {0} for {1} has been confirmed".format(benefit.benefit, benefit.sponsor),
						 sendername=conference.conferencename,
						 )

@login_required
def sponsor_admin_sponsor(request, confurlname, sponsorid):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confurlname)
	else:
		conference = get_object_or_404(Conference, urlname=confurlname, administrators=request.user)

	sponsor = get_object_or_404(Sponsor, id=sponsorid, conference=conference)

	if request.method == 'POST' and request.POST['confirm'] == '1':
		# Confirm one of the benefits, so do this before we load the list
		benefit = get_object_or_404(SponsorClaimedBenefit, sponsor=sponsor, id=request.POST['claimid'])
		_confirm_benefit(request, benefit)
		return HttpResponseRedirect('.')

	unclaimedbenefits = SponsorshipBenefit.objects.filter(level=sponsor.level, benefit_class__isnull=False).exclude(sponsorclaimedbenefit__sponsor=sponsor)
	claimedbenefits = SponsorClaimedBenefit.objects.filter(sponsor=sponsor).order_by('confirmed', 'benefit__sortkey')
	noclaimbenefits = SponsorshipBenefit.objects.filter(level=sponsor.level, benefit_class__isnull=True)

	for b in claimedbenefits:
		if b.benefit.benefit_class:
			b.claimhtml = get_benefit_class(b.benefit.benefit_class)(sponsor.level, b.benefit.class_parameters).render_claimdata(b)


	return render(request, 'confsponsor/admin_sponsor.html', {
		'conference': conference,
		'sponsor': sponsor,
		'claimedbenefits': claimedbenefits,
		'unclaimedbenefits': unclaimedbenefits,
		'noclaimbenefits': noclaimbenefits,
		'breadcrumbs': (('/events/sponsor/admin/{0}/'.format(conference.urlname), 'Sponsors'),),
		'euvat': settings.EU_VAT,
		})

@login_required
@transaction.atomic
def sponsor_admin_generateinvoice(request, confurlname, sponsorid):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confurlname)
	else:
		conference = get_object_or_404(Conference, urlname=confurlname, administrators=request.user)

	sponsor = get_object_or_404(Sponsor, id=sponsorid, conference=conference)

	if sponsor.invoice:
	    # Existing invoice
		messages.warning(request, "This sponsor already has an invoice!")
		return HttpResponseRedirect("../")

	# Actually generate the invoice!
	manager = sponsor.managers.all()[0]
	sponsor.invoice = create_sponsor_invoice(manager, sponsor)
	sponsor.invoice.save()
	sponsor.save()
	wrapper = InvoiceWrapper(sponsor.invoice)
	wrapper.email_invoice()
	return HttpResponseRedirect("../")

@login_required
@transaction.atomic
def sponsor_admin_confirm(request, confurlname, sponsorid):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confurlname)
	else:
		conference = get_object_or_404(Conference, urlname=confurlname, administrators=request.user)

	sponsor = get_object_or_404(Sponsor, id=sponsorid, conference=conference)

	confirm_sponsor(sponsor, request.user.username)

	return HttpResponseRedirect('../')

@login_required
def sponsor_admin_benefit(request, confurlname, benefitid):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confurlname)
	else:
		conference = get_object_or_404(Conference, urlname=confurlname, administrators=request.user)

	benefit = get_object_or_404(SponsorClaimedBenefit, id=benefitid, sponsor__conference=conference)
	if benefit.benefit.benefit_class:
		claimdata = get_benefit_class(benefit.benefit.benefit_class)(benefit.benefit.level, benefit.benefit.class_parameters).render_claimdata(benefit)
	else:
		claimdata = None

	if request.method == 'POST' and request.POST.get('confirm', '') == '1':
		# Confirm this benefit!
		_confirm_benefit(request, benefit)
		return HttpResponseRedirect('.')

	if request.method == 'POST' and request.POST.get('unclaim', '') == '1':
		# Un-claim this benefit. That means we just remove the SponsorClaimedBenefit entry
		benefit.delete()
		messages.info(request, "The benefit {0} has been un-claimed from {1}".format(benefit.benefit, benefit.sponsor))
		return HttpResponseRedirect('../../')

	return render(request, 'confsponsor/admin_benefit.html', {
		'conference': conference,
		'sponsor': benefit.sponsor,
		'benefit': benefit,
		'claimdata': claimdata,
		'breadcrumbs': (('/events/sponsor/admin/{0}/'.format(conference.urlname), 'Sponsors'),),
		})

@login_required
@transaction.atomic
def sponsor_admin_send_mail(request, confurlname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confurlname)
	else:
		conference = get_object_or_404(Conference, urlname=confurlname, administrators=request.user)

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
			for sponsor in sponsors:
				msgtxt = u"{0}\n\n-- \nThis message was sent to sponsors of {1}.\nYou can view all communications for this conference at:\n{2}/events/sponsor/{3}/\n".format(msg.message, conference, settings.SITEBASE, sponsor.pk)
				for manager in sponsor.managers.all():
					send_simple_mail(conference.sponsoraddr,
									 manager.email,
									 u"[{0}] {1}".format(conference, msg.subject),
									 msgtxt,
									 sendername=conference.conferencename,
									 receivername=u'{0} {1}'.format(manager.first_name, manager.last_name))

			send_simple_mail(conference.sponsoraddr,
							 conference.sponsoraddr,
							 "Email sent to sponsors",
							 "An email was sent to sponsors of {0}.\n\nTo view it, go to {1}/events/sponsor/admin/{2}/viewmail/{3}/".format(conference, settings.SITEBASE, conference.urlname, msg.id),
							 sendername=conference.conferencename,
							 receivername=conference.conferencename)

			messages.info(request, "Email sent to %s sponsors, and added to all sponsor pages" % len(sponsors))
			return HttpResponseRedirect("../")
	else:
		form = SponsorSendEmailForm(conference)

	return render(request, 'confsponsor/sendmail.html', {
		'conference': conference,
		'form': form,
		'mails': SponsorMail.objects.filter(conference=conference).order_by('sentat'),
		'breadcrumbs': (('/events/sponsor/admin/{0}/'.format(conference.urlname), 'Sponsors'),),
	})

@login_required
def sponsor_admin_view_mail(request, confurlname, mailid):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confurlname)
	else:
		conference = get_object_or_404(Conference, urlname=confurlname, administrators=request.user)

	mail = get_object_or_404(SponsorMail, conference=conference, id=mailid)
	return render(request, 'confsponsor/sent_mail.html', {
		'conference': conference,
		'mail': mail,
		'admin': True,
		'breadcrumbs': (('/events/sponsor/admin/{0}/'.format(conference.urlname), 'Sponsors'),),
		})

@login_required
def sponsor_admin_imageview(request, benefitid):
	# Image is fetched as part of a benefit, so find the benefit

	benefit = get_object_or_404(SponsorClaimedBenefit, id=benefitid)
	if not request.user.is_superuser:
		# Check permissions for non superusers
		if not benefit.sponsor.conference.administrators.filter(pk=request.user.id).exists():
			# Finally, can actually be viewed by the managers of the
			# sponsor itself.
			if not benefit.sponsor.managers.filter(pk=request.user.id).exists():
				return HttpResponseForbidden("Access denied")

	# If the benefit existed, we have verified the permissions, so we can now show
	# the image itself.
	storage = InlineEncodedStorage('benefit_image')
	f = storage.open(str(benefit.id))
	if f is None:
		raise Http404('Benefit image not found')

	# XXX: do we need to support non-png at some point? store info in claimdata!
	resp = HttpResponse(content_type='image/png')
	resp.write(f.read())
	return resp

@login_required
@transaction.atomic
def admin_copy_level(request, levelid):
	if not request.user.is_superuser:
		raise Exception("Sorry, at this point only superusers can do this")

	level = get_object_or_404(SponsorshipLevel, id=levelid)

	if request.method == 'POST':
		form = AdminCopySponsorshipLevelForm(data=request.POST)
		if form.is_valid():
			targetconf = Conference.objects.get(pk=form.data['targetconference'])
			newlevel = get_object_or_404(SponsorshipLevel, id=levelid)
			# Set pk to none to copy object
			newlevel.pk = None
			if targetconf == level.conference:
				newlevel.levelname = 'Copy of {0}'.format(level.levelname)
				newlevel.urlname = 'copy_of_{0}'.format(level.urlname)
			else:
				newlevel.conference = targetconf
			newlevel.save()
			for pm in level.paymentmethods.all():
				newlevel.paymentmethods.add(pm)
			newlevel.save()
			for b in level.sponsorshipbenefit_set.all():
				b.pk = None
				b.level = newlevel
				b.save()
			return HttpResponseRedirect("/admin/confsponsor/sponsorshiplevel/{0}/".format(newlevel.id))
	else:
		form = AdminCopySponsorshipLevelForm()

	return render(request, 'confsponsor/admin_copy_level.html', {
		'form': form,
		'sourcelevel': level,
	})

@login_required
@user_passes_test_or_error(lambda u: u.is_superuser)
def sponsor_admin_test_vat(request, confurlname):
	conference = get_object_or_404(Conference, urlname=confurlname)

	vn = request.POST.get('vatnumber', '')
	if not vn:
		return HttpResponse("Empty search")

	r = validate_eu_vat_number(vn)
	if r:
		return HttpResponse("VAT validation error: %s" % r)
	return HttpResponse("VAT number is valid")

