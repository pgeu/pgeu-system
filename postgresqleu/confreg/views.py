#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponsePermanentRedirect, HttpResponse, Http404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.db import transaction, connection
from django.db.models import Q, Count, Avg
from django.db.models.expressions import F
from django.forms import formsets
from django.forms import ValidationError

from models import Conference, ConferenceRegistration, ConferenceSession
from models import ConferenceSessionSlides, ConferenceSessionVote, GlobalOptOut
from models import ConferenceSessionFeedback, Speaker, Speaker_Photo
from models import ConferenceFeedbackQuestion, ConferenceFeedbackAnswer
from models import RegistrationType, PrepaidVoucher, PrepaidBatch
from models import BulkPayment, Room, Track, ConferenceSessionScheduleSlot
from models import AttendeeMail, ConferenceAdditionalOption
from models import PendingAdditionalOrder
from models import RegistrationWaitlistEntry, RegistrationWaitlistHistory
from models import STATUS_CHOICES
from models import ConferenceNews
from forms import ConferenceRegistrationForm, RegistrationChangeForm, ConferenceSessionFeedbackForm
from forms import ConferenceFeedbackForm, SpeakerProfileForm
from forms import CallForPapersForm, CallForPapersSpeakerForm
from forms import CallForPapersCopyForm, PrepaidCreateForm, BulkRegistrationForm
from forms import EmailSendForm, EmailSessionForm, CrossConferenceMailForm
from forms import AttendeeMailForm, WaitlistOfferForm, TransferRegForm
from forms import NewMultiRegForm, MultiRegInvoiceForm
from forms import SessionSlidesUrlForm, SessionSlidesFileForm
from util import invoicerows_for_registration, notify_reg_confirmed, InvoicerowsException
from util import get_invoice_autocancel, cancel_registration

from models import get_status_string
from regtypes import confirm_special_reg_type, validate_special_reg_type
from jinjafunc import render_jinja_conference_response, JINJA_TEMPLATE_ROOT
from backendviews import get_authenticated_conference

from postgresqleu.util.decorators import superuser_required
from postgresqleu.util.random import generate_random_token
from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod, InvoiceRow
from postgresqleu.confwiki.models import Wikipage
from postgresqleu.invoices.util import InvoiceManager, InvoicePresentationWrapper
from postgresqleu.invoices.models import InvoiceProcessor, InvoiceHistory
from postgresqleu.mailqueue.util import send_mail, send_simple_mail, send_template_mail, template_to_string
from postgresqleu.util.jsonutil import JsonSerializer
from postgresqleu.util.db import exec_to_dict, exec_to_grouped_dict, exec_to_keyed_dict
from postgresqleu.util.db import exec_no_result, exec_to_list, exec_to_scalar, conditional_exec_to_scalar

from decimal import Decimal
from operator import itemgetter
from datetime import datetime, timedelta, date
import base64
import re
import os
from email.mime.text import MIMEText
from Crypto.Hash import SHA256
from StringIO import StringIO

import json
import markdown

#
# Render a conference page. It will load the template using the jinja system
# if the conference is configured for jinja templates.
#
def render_conference_response(request, conference, pagemagic, templatename, dictionary=None):
	if not conference:
		raise Exception("Conference has to be specified!")

	if conference.jinjadir:
		# If a jinjadir is defined, then *always* use jinja.
		return render_jinja_conference_response(request, conference, pagemagic, templatename, dictionary)

	# At this point all conference templates are in jinja except the admin ones, and admin does not render
	# through render_conference_response(). Thus, if it's not here now, we can 404.
	if os.path.exists(os.path.join(JINJA_TEMPLATE_ROOT, templatename)):
		return render_jinja_conference_response(request, conference, pagemagic, templatename, dictionary)

	raise Http404("Template not found")

def _get_registration_signups(conference, reg):
	# Left join is hard to do efficiently with the django ORM, so let's do a query instead
	cursor = connection.cursor()
	cursor.execute("SELECT s.id, s.title, s.deadline, s.deadline < CURRENT_TIMESTAMP, ats.saved FROM confwiki_signup s LEFT JOIN confwiki_attendeesignup ats ON (s.id=ats.signup_id AND ats.attendee_id=%(regid)s) WHERE s.conference_id=%(confid)s AND (s.deadline IS NULL OR s.deadline > CURRENT_TIMESTAMP OR ats.saved IS NOT NULL) AND (s.public OR EXISTS (SELECT 1 FROM confwiki_signup_attendees sa WHERE sa.signup_id=s.id AND sa.conferenceregistration_id=%(regid)s) OR EXISTS (SELECT 1 FROM confwiki_signup_regtypes sr WHERE sr.signup_id=s.id AND sr.registrationtype_id=%(regtypeid)s)) ORDER  BY 4 DESC, 3, 2", {
		'confid': conference.id,
		'regid': reg.id,
		'regtypeid': reg.regtype_id,
		})
	return [dict(zip(['id', 'title', 'deadline', 'closed', 'savedat'], r)) for r in cursor.fetchall()]

# Not a view in itself, only called from other views
def _registration_dashboard(request, conference, reg, has_other_multiregs, redir_root):
	mails = AttendeeMail.objects.filter(conference=conference, regclasses=reg.regtype.regclass)

	wikipagesQ = Q(publicview=True) | Q(viewer_attendee__attendee=request.user) | Q(viewer_regtype__conferenceregistration__attendee=request.user)
	wikipages = Wikipage.objects.filter(Q(conference=conference) & wikipagesQ).distinct()

	signups = _get_registration_signups(conference, reg)

	is_speaker = ConferenceSession.objects.filter(conference=conference, status=1, speaker__user=request.user).exists()

	# Options available for buy-up. Option must be for this conference,
	# not already picked by this user, and not mutually exclusive to
	# anything picked by this user.
	# Also exclude any option that has a maxcount, and already has too
	# many registrations.
	optionsQ = Q(conference=conference, upsellable=True, public=True) & (Q(maxcount=0) | Q(num_regs__lt=F('maxcount'))) & ~Q(conferenceregistration=reg) & ~Q(mutually_exclusive__conferenceregistration=reg)
	availableoptions = list(ConferenceAdditionalOption.objects.annotate(num_regs=Count('conferenceregistration')).filter(optionsQ))
	try:
		pendingadditional = PendingAdditionalOrder.objects.get(reg=reg, payconfirmedat__isnull=True)
		pendingadditionalinvoice = InvoicePresentationWrapper(pendingadditional.invoice, '.')
	except PendingAdditionalOrder.DoesNotExist:
		pendingadditional = None
		pendingadditionalinvoice = None

	# Any invoices that should be linked need to be added
	invoices = []
	if reg.invoice:
		invoices.append(('Registration invoice and receipt', InvoicePresentationWrapper(reg.invoice,'.')))
	for pao in PendingAdditionalOrder.objects.filter(reg=reg, invoice__isnull=False):
		invoices.append(('Additional options invoice and receipt', InvoicePresentationWrapper(pao.invoice, '.')))

	if conference.allowedit:
		# Form for changeable fields
		if request.method == 'POST':
			changeform = RegistrationChangeForm(instance=reg, data=request.POST)
			if changeform.is_valid():
				changeform.save()
				messages.info(request, "Registration updated.")
				return HttpResponseRedirect("../")
		else:
			changeform = RegistrationChangeForm(instance=reg)
	else:
		changeform = None

	fields = ['shirtsize', 'dietary', 'nick', 'twittername', 'shareemail', 'photoconsent']
	for f in conference.remove_fields:
		fields.remove(f)
	displayfields = [(reg._meta.get_field(k).verbose_name.capitalize(), reg.get_field_string(k)) for k in fields]

	return render_conference_response(request, conference, 'reg', 'confreg/registration_dashboard.html', {
		'redir_root': redir_root,
		'reg': reg,
		'is_speaker': is_speaker,
		'has_other_multiregs': has_other_multiregs,
		'mails': mails,
		'wikipages': wikipages,
		'signups': signups,
		'availableoptions': availableoptions,
		'pendingadditional': pendingadditional,
		'pendingadditionalinvoice': pendingadditionalinvoice,
		'invoices': invoices,
		'changeform': changeform,
		'displayfields': displayfields,
	})

def confhome(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	# If there is a registration, redirect to the registration dashboard.
	# If not, or if the user is not logged in, redirect to the conference homepage.
	if request.user.is_authenticated():
		if ConferenceRegistration.objects.filter(conference=conference, attendee=request.user).exists():
			return HttpResponseRedirect('register/')

	return HttpResponseRedirect(conference.confurl)

def news_json(request, confname):
	news = ConferenceNews.objects.select_related('author').filter(conference__urlname=confname,
																  inrss=True,
																  datetime__lt=datetime.now(),
	)[:5]

	r = HttpResponse(json.dumps(
		[{
			'title': n.title,
			'datetime': n.datetime,
			'authorname': n.author.fullname,
			'summary': markdown.markdown(n.summary),
		} for n in news],
		cls=JsonSerializer), content_type='application/json')

	r['Access-Control-Allow-Origin'] = '*'
	return r


@login_required
@transaction.atomic
def register(request, confname, whatfor=None):
	conference = get_object_or_404(Conference, urlname=confname)
	if whatfor:
		whatfor = whatfor.rstrip('/')
		redir_root = '../'
	else:
		redir_root = ''

	has_other_multiregs = ConferenceRegistration.objects.filter(Q(conference=conference, registrator=request.user) & ~Q(attendee=request.user)).exists()
	if (not whatfor) and has_other_multiregs and \
	   not ConferenceRegistration.objects.filter(conference=conference, attendee=request.user).exists():
		return HttpResponseRedirect('other/')

	# Either not specifying or registering for self.
	try:
		reg = ConferenceRegistration.objects.get(conference=conference,
												 attendee=request.user)
	except ConferenceRegistration.DoesNotExist:
		# No previous registration exists. Let the user choose what to
		# do. If already under "self" suburl, copy the data from the
		# user profile and move on.
		if whatfor == None:
			return render_conference_response(request, conference, 'reg', 'confreg/prompt_regfor.html')

		# No previous registration, grab some data from the user profile
		reg = ConferenceRegistration(conference=conference, attendee=request.user)
		reg.email = request.user.email
		reg.firstname = request.user.first_name
		reg.lastname = request.user.last_name
		reg.created = datetime.now()
		reg.regtoken = generate_random_token()

	is_active = conference.active or conference.testers.filter(pk=request.user.id).exists()

	if not is_active:
		# Registration not open.
		if reg.payconfirmedat:
			# Attendee has a completed registration, but registration is closed.
			# Render the dashboard.
			return _registration_dashboard(request, conference, reg, has_other_multiregs, redir_root)
		else:
			return render_conference_response(request, conference, 'reg', 'confreg/closed.html')

	# Else registration is open.

	if reg.invoice and not reg.payconfirmedat:
		# Pending invoice exists. See if it should be canceled.
		if reg.invoice.canceltime and reg.invoice.canceltime < datetime.now():
			# Yup, should be canceled
			manager = InvoiceManager()
			manager.cancel_invoice(reg.invoice,
								   "Invoice was automatically canceled because payment was not received on time.")

			# cancel_invoice will call the processor to unlink the invoice,
			# so make sure we refresh the object.
			reg = ConferenceRegistration.objects.get(id=reg.id)

	form_is_saved = False
	if request.method == 'POST':
		# Attempting to modify the registration
		if reg.bulkpayment:
			return render_conference_response(request, conference, 'reg', 'confreg/bulkpayexists.html')
		if reg.invoice:
			return render_conference_response(request, conference, 'reg', 'confreg/invoiceexists.html')

		# Did the user click cancel? We want to check that before we
		# check form.is_valid(), to avoid the user getting errors like
		# "you must specify country in order to cancel".
		if request.POST['submit'] == 'Cancel registration':
			if reg.id:
				reg.delete()
			return HttpResponseRedirect("{0}canceled/".format(redir_root))


		form = ConferenceRegistrationForm(request.user, data=request.POST, instance=reg)
		if form.is_valid():
			reg = form.save(commit=False)
			reg.conference = conference
			reg.attendee = request.user
			reg.registrator = request.user
			reg.save()
			form.save_m2m()
			form_is_saved = True

			# Figure out if the user clicked a "magic save button"
			if request.POST['submit'] == 'Confirm and finish' or request.POST['submit'] == 'Save and finish':
				# Complete registration!
				return HttpResponseRedirect("{0}confirm/".format(redir_root))

			# Or did they click cancel?
			if request.POST['submit'] == 'Cancel registration':
				reg.delete()
				return HttpResponseRedirect("{0}canceled/".format(redir_root))

			# Or did they save but we're on the "wrong" url
			if redir_root:
				return HttpResponseRedirect(redir_root)

			# Else it was a general save, and we'll fall through and
			# show the form again so details can be edited.
	else:
		# This is just a get. Depending on the state of the registration,
		# we may want to show the form or not.
		if reg.payconfirmedat:
			# This registration is completed. Show the dashboard instead of
			# the registration form.
			return _registration_dashboard(request, conference, reg, has_other_multiregs, redir_root)

		if reg.invoice or reg.bulkpayment:
			# Invoice generated or part of bulk payment means the registration
			# can't be changed any more (without having someone cancel the
			# invoice).

			return render_conference_response(request, conference, 'reg', 'confreg/regform_completed.html', {
				'reg': reg,
				'redir_root': redir_root,
				'invoice': InvoicePresentationWrapper(reg.invoice, "%s/events/%s/register/" % (settings.SITEBASE, conference.urlname)),
			})

		# Else fall through and render the form
		form = ConferenceRegistrationForm(request.user, instance=reg)

	return render_conference_response(request, conference, 'reg', 'confreg/regform.html', {
		'form': form,
		'form_is_saved': form_is_saved,
		'reg': reg,
		'redir_root': redir_root,
		'invoice': InvoicePresentationWrapper(reg.invoice, "%s/events/%s/register/" % (settings.SITEBASE, conference.urlname)),
		'additionaloptions': conference.conferenceadditionaloption_set.filter(public=True),
		'costamount': reg.regtype and reg.regtype.cost or 0,
	})

@login_required
@transaction.atomic
def changereg(request, confname):
	# Change certain allowed fields on a registration.
	conference = get_object_or_404(Conference, urlname=confname)
	reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user)

	if not conference.allowedit:
		return HttpResponseRedirect('../')

	return _registration_dashboard(request, conference, reg, False, '../')

@login_required
@transaction.atomic
def multireg(request, confname, regid=None):
	# "Register for somebody else" functionality.
	conference = get_object_or_404(Conference, urlname=confname)
	is_active = conference.active or conference.testers.filter(pk=request.user.id).exists()
	if not is_active:
		# Registration not open.
		return render_conference_response(request, conference, 'reg', 'confreg/closed.html')

	allregs = ConferenceRegistration.objects.filter(conference=conference, registrator=request.user)
	try:
		(a for a in allregs if not (a.payconfirmedat or a.bulkpayment)).next()
		haspending = True
	except StopIteration:
		haspending = False

	if regid:
		# Editing a specific registration
		regid = regid.rstrip('/')
		reg = get_object_or_404(ConferenceRegistration,
								pk=regid,
								conference=conference,
								registrator=request.user)
		redir_root='../'
	else:
		reg = ConferenceRegistration(conference=conference,
									 registrator=request.user,
									 created=datetime.now(),
									 regtoken=generate_random_token(),
		)
		redir_root='./'


	if request.method == 'POST':
		if request.POST['submit'] == 'New registration':
			# New registration form
			newform = NewMultiRegForm(conference, data=request.POST)
			if newform.is_valid():
				# Create a registration form for the details, and render
				# a separate page for it.
				# Create a registration but don't save it until we have
				# details entered.
				reg.email = newform.cleaned_data['email']
				regform = ConferenceRegistrationForm(request.user, instance=reg, regforother=True)
				return render_conference_response(request, conference, 'reg', 'confreg/regmulti_form.html', {
					'form': regform,
					'_email': newform.cleaned_data['email'],
				})
		elif request.POST['submit'] == 'Cancel':
			return HttpResponseRedirect(redir_root)
		elif request.POST['submit'] == 'Delete':
			if reg.pk:
				# Only delete if it has a primary key. Not having a primary key means
				# it was never saved, so there is nothing to delete.
				reg.delete()
			return HttpResponseRedirect(redir_root)
		elif request.POST['submit'] == 'Save':
			reg.email = request.POST['_email']
			regform = ConferenceRegistrationForm(request.user, data=request.POST, instance=reg, regforother=True)
			if regform.is_valid():
				reg = regform.save(commit=False)
				reg.conference = conference
				reg.registrator = request.user
				reg.attendee = None
				reg.save()
				regform.save_m2m()
				return HttpResponseRedirect(redir_root)
			else:
				return render_conference_response(request, conference, 'reg', 'confreg/regmulti_form.html', {
					'form': regform,
				})
		else:
			return HttpResponse("Unknown button pressed")
			newform = None
	else:
		if regid:
			# Editing a specific registration
			reg = get_object_or_404(ConferenceRegistration,
									pk=regid,
									conference=conference,
									registrator=request.user)
			regform = ConferenceRegistrationForm(request.user, instance=reg, regforother=True)
			return render_conference_response(request, conference, 'reg', 'confreg/regmulti_form.html', {
				'form': regform,
			})
		else:
			# Root page, so just render the base form
			newform = NewMultiRegForm(conference)

	return render_conference_response(request, conference, 'reg', 'confreg/regmulti.html', {
		'newform': newform,
		'allregs': allregs,
		'haspending': haspending,
		'activewaitlist': conference.waitlist_active(),
		'bulkpayments': BulkPayment.objects.filter(conference=conference, user=request.user),
	})


def _create_and_assign_bulk_payment(user, conference, regs, invoicerows, recipient_name, recipient_address, send_mail):
	autocancel_hours = [conference.invoice_autocancel_hours, ]

	bp = BulkPayment()
	bp.user = user
	bp.conference = conference
	bp.numregs = len(regs)
	bp.save()

	for r in regs:
		r.bulkpayment = bp
		r.save()

		autocancel_hours.append(r.regtype.invoice_autocancel_hours)
		autocancel_hours.extend([a.invoice_autocancel_hours for a in r.additionaloptions.filter(invoice_autocancel_hours__isnull=False)])

		if send_mail:
			# Also notify these registrants that they have been
			# added to the bulk payment.
			send_template_mail(conference.contactaddr,
							   r.email,
							   "Your registration for {0} added to bulk payment".format(conference.conferencename),
							   'confreg/mail/bulkpay_added.txt',
							   {
								   'conference': conference,
								   'reg': r,
								   'bulk': bp,
							   },
							   sendername = conference.conferencename,
							   receivername = r.fullname,
			)

	# Now that our bulkpayment is complete, create an invoice for it
	manager = InvoiceManager()
	processor = InvoiceProcessor.objects.get(processorname="confreg bulk processor")

	if bp.numregs > 1:
		invoicetitle = '%s multiple registrations' % conference.conferencename
	else:
		invoicetitle = "%s registration" % conference.conferencename
	bp.invoice = manager.create_invoice(
		user,
		user.email,
		recipient_name,
		recipient_address,
		invoicetitle,
		datetime.now(),
		datetime.now(),
		invoicerows,
		processor=processor,
		processorid = bp.pk,
		bankinfo = False,
		accounting_account = settings.ACCOUNTING_CONFREG_ACCOUNT,
		accounting_object = conference.accounting_object,
		canceltime = get_invoice_autocancel(*autocancel_hours),
	)
	bp.invoice.save()
	bp.save()

	return bp

@login_required
@transaction.atomic
def multireg_newinvoice(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	is_active = conference.active or conference.testers.filter(pk=request.user.id).exists()
	if not is_active:
		# Registration not open.
		return render_conference_response(request, conference, 'reg', 'confreg/closed.html')

	if request.method == 'POST' and request.POST['submit'] == 'Cancel':
		return HttpResponseRedirect('../')

	# Collect all pending regs
	pendingregs = ConferenceRegistration.objects.filter(conference=conference,
														registrator=request.user,
														payconfirmedat__isnull=True,
														invoice__isnull=True,
														bulkpayment__isnull=True)
	if not pendingregs.exists():
		# No pending registrations exist, so just send back (should not
		# happen scenario)
		return HttpResponseRedirect('../')

	finalize = (request.method == 'POST' and request.POST['submit'] == 'Create')
	if finalize:
		savepoint = transaction.savepoint()

	# Almost like a bulk invoice, but we know the registrations were
    # created so they exist.
	errors = []
	invoicerows = []
	for r in pendingregs:
		if not r.regtype:
			errors.append(u'{0} has no registration type specified'.format(r.email))
		elif not r.regtype.active:
			errors.append(u'{0} uses registration type {1} which is not active'.format(r.email, r.regtype))
		elif r.regtype.activeuntil and r.regtype.activeuntil < date.today():
			errors.append(u'{0} uses registration type {1} which is not active'.format(r.email, r.regtype))
		else:
			try:
				invoicerows.extend(invoicerows_for_registration(r, finalize))
			except InvoicerowsException, ex:
				errors.append(u'{0}: {1}'.format(r.email, ex))

	for r in invoicerows:
		# Calculate the with-vat information for this row
		if r[3]:
			r.append(r[2]*(100+r[3].vatpercent)/Decimal(100))
		else:
			r.append(r[2])
	totalcost = sum([r[2] for r in invoicerows])
	totalwithvat = sum([r[4] for r in invoicerows])

	if finalize:
		form = MultiRegInvoiceForm(data=request.POST)
		if totalwithvat != Decimal(request.POST['totalwithvat']):
			errors.append('Total amount has changed, likely due to a registration being concurrently changed. Please try again.')
			# Error set, so will fall through into the path that rolls back

		if form.is_valid() and not errors:
			if totalwithvat == 0:
				errors.append('Should never happen, invoice should have already been bypassed for zero')
				# Fall through to render with errors
			else:
				# Else generate a bulk payment and invoice for it
				bp = _create_and_assign_bulk_payment(request.user,
													 conference,
													 pendingregs,
													 invoicerows,
													 form.data['recipient'],
													 form.data['address'],
													 False)

				return HttpResponseRedirect("../b{0}/".format(bp.id))

		# If we flagged discount codes etc as used, but came down her in the error path,
	    # make sure we roll back the change.
		transaction.savepoint_rollback(savepoint)

		# Add the errors to the form, so they're actually visible.
		for e in errors:
			form.add_error(None, e)
	else:
		# No need to show the form in case we actually have a total cost of zero.
		# Instead, just immediately flag them as used.
		if totalwithvat == 0 and not errors:
			for r in pendingregs:
				# Flag discount code/vouchers as used
				invoicerows_for_registration(r, True)
				# Now mark the registration as done.
				r.payconfirmedat = datetime.now()
				r.payconfirmedby = "Multireg/nopay"
				r.save()
				notify_reg_confirmed(r)
			return HttpResponseRedirect("../z/")

		form = MultiRegInvoiceForm()


	return render_conference_response(request, conference, 'reg', 'confreg/regmulti_invoice.html', {
		'form': form,
		'invoicerows': invoicerows,
		'totalcost': totalcost,
		'totalwithvat': totalwithvat,
	})

@login_required
def multireg_zeropay(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	return render_conference_response(request, conference, 'reg', 'confreg/regmulti_zeropay.html', {
	})

@login_required
@transaction.atomic
def multireg_bulkview(request, confname, bulkid):
	conference = get_object_or_404(Conference, urlname=confname)
	is_active = conference.active or conference.testers.filter(pk=request.user.id).exists()
	if not is_active:
		# Registration not open.
		return render_conference_response(request, conference, 'reg', 'confreg/closed.html')

	bp = get_object_or_404(BulkPayment, conference=conference, pk=bulkid, user=request.user)

	return render_conference_response(request, conference, 'reg', 'confreg/regmulti_bulk.html', {
		'bulkpayment': bp,
		'invoice': InvoicePresentationWrapper(bp.invoice, '.'),
	})

@login_required
@transaction.atomic
def multireg_attach(request, token):
	reg = get_object_or_404(ConferenceRegistration, regtoken=token)
	if reg.attendee:
		return HttpResponse("This registration has already been attached to an account")

	conference = reg.conference
	if ConferenceRegistration.objects.filter(conference=conference, attendee=request.user).exists():
		return HttpResponse("Logged in user ({0}) already has a registration at this conference".format(request.user.username))

	# Else we ask the user to confirm
	if request.method == "POST" and request.POST['submit'] == 'Confirm and attach account':
		reg.attendee = request.user
		reg.save()
		return HttpResponseRedirect('/events/register/{0}/'.format(conference.urlname))
	else:
		return render_conference_response(request, conference, 'reg', 'confreg/regmulti_attach.html', {
			'reg': reg,
		})

def feedback_available(request):
	conferences = Conference.objects.filter(feedbackopen=True).order_by('startdate')
	return render(request, 'confreg/feedback_available.html', {
		'conferences': conferences,
	})

@login_required
@transaction.atomic
def reg_add_options(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	reg = get_object_or_404(ConferenceRegistration, conference=conference, attendee=request.user)

	if not reg.payconfirmedat:
		messages.warning(request, "Registration not confirmed, should not get here")
		return HttpResponseRedirect('../')

	if request.POST.get('submit', '') == 'Back':
		return HttpResponseRedirect('../')

	options = []
	for k,v in request.POST.items():
		if k.startswith('ao_') and v == "1":
			options.append(int(k[3:]))

	if not len(options) > 0:
		messages.info(request, "No additional options selected, nothing to order")
		return HttpResponseRedirect('../')

	options = ConferenceAdditionalOption.objects.filter(conference=conference, pk__in=options, upsellable=True)
	if len(options) < 0:
		messages.warning(request, "Option searching mismatch, order canceled.")

	# Check the count on each option (yes, this is inefficient, but who cares)
	for o in options:
		if o.maxcount > 0:
			if o.conferenceregistration_set.count() >= o.maxcount:
				messages.warning(request, "Option '{0}' is sold out.".format(o.name))
				return HttpResponseRedirect('../')

	# Check if any of the options are mutually exclusive
	for o in options:
		for x in o.mutually_exclusive.all():
			if x in options:
				messages.warning(request, "Option '{0}' can't be ordered at the same time as '{1}'".format(o.name, x.name))
				return HttpResponseRedirect('../')

	# Check if any of the options require a different regtype,
	# and that this regtype is upsellable.
	new_regtype = None
	for o in options:
		a = o.requires_regtype.all()
		if a and not reg.regtype in a:
			# New regtype is required. Figure out if there is an upsellable
			# one available.
			upsellable = o.requires_regtype.filter(Q(upsell_target=True, active=True, specialtype__isnull=True) & (Q(activeuntil__isnull=True) | Q(activeuntil__lt=datetime.today().date())))
			l = len(upsellable)
			if l == 0:
				messages.warning(request, "Option {0} requires a registration type that's not available.".format(o.name))
				return HttpResponseRedirect('../')
			elif l > 1:
				messages.warning(request, "Option {0} requires a registration type that cannot be automaticalliy selected. Please email the organizers to make your registration.".format(o.name))
				return HttpResponseRedirect('../')
			if new_regtype:
				# A new registration type has been selected by another option
				# so we need to verify if it's the same.
				if new_regtype != upsellable[0]:
					messages.warning(request, "Requested options require different registration types, and cannot be ordered.")
					return HttpResponseRedirect('../')
			else:
				new_regtype = upsellable[0]

	if new_regtype and new_regtype.cost >= reg.regtype.cost:
		upsell_cost = new_regtype.cost - reg.regtype.cost
	else:
		upsell_cost = 0

	# Build our invoice rows
	invoicerows = []
	autocancel_hours = [conference.invoice_autocancel_hours, ]
	if upsell_cost:
		invoicerows.append(['Upgrade to {0}'.format(new_regtype.regtype), 1, upsell_cost, conference.vat_registrations])
		if new_regtype.invoice_autocancel_hours:
			autocancel_hours.append(new_regtype.invoice_autocancel_hours)

	for o in options:
		# Yes, we include €0 options for completeness.
		invoicerows.append([o.name, 1, o.cost, conference.vat_registrations])
		if o.invoice_autocancel_hours:
			autocancel_hours.append(o.invoice_autocancel_hours)

	# Add VAT information to invoice rows
	for r in invoicerows:
		# Calculate the with-vat information for this row
		if r[3]:
			r.append(r[2]*(100+r[3].vatpercent)/Decimal(100))
		else:
			r.append(r[2])

	totalcost = sum([r[2] for r in invoicerows])
	totalwithvat = sum([r[4] for r in invoicerows])

	if not request.POST.get('confirm', None) == 'yes':
		# Generate a preview
		return render_conference_response(request, conference, 'reg', 'confreg/confirm_addons.html', {
			'reg': reg,
			'options': options,
			'invoicerows': invoicerows,
			'totalcost': totalcost,
			'totalwithvat': totalwithvat,
		})
	else:
		if totalcost == 0:
			# No payment, but possibly update the registration type, and
			# definitely add the option.
			if new_regtype:
				reg.regtype = new_regtype
			for o in options:
				reg.additionaloptions.add(o)
			reg.save()
			messages.info(request, 'Additional options added to registration')
			return HttpResponseRedirect('../')

		# Create a pending addon order, and generate an invoice
		order = PendingAdditionalOrder(reg=reg,
									   createtime=datetime.now())
		if new_regtype:
			order.newregtype = new_regtype

		order.save() # So we get a PK and can add m2m values
		for o in options:
			order.options.add(o)

		manager = InvoiceManager()
		processor = InvoiceProcessor.objects.get(processorname='confreg addon processor')
		order.invoice = manager.create_invoice(
			request.user,
			request.user.email,
			reg.firstname + ' ' + reg.lastname,
			reg.company + "\n" + reg.address + "\n" + reg.country.name,
			"%s additional options" % conference.conferencename,
			datetime.now(),
			datetime.now(),
			invoicerows,
			processor = processor,
			processorid = order.pk,
			bankinfo = False,
			accounting_account = settings.ACCOUNTING_CONFREG_ACCOUNT,
			accounting_object = conference.accounting_object,
			canceltime = get_invoice_autocancel(*autocancel_hours),
		)
		order.invoice.save()
		order.save()

		# Redirect the user to the invoice
		return HttpResponseRedirect('/invoices/{0}/{1}/'.format(order.invoice.id, order.invoice.recipient_secret))


@login_required
def feedback(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.feedbackopen:
		# Allow conference testers to override
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'feedback', 'confreg/feedbackclosed.html')
		else:
			is_conf_tester = True
	else:
		is_conf_tester = False

	# Figure out if the user is registered
	try:
		r = ConferenceRegistration.objects.get(conference=conference, attendee=request.user)
	except ConferenceRegistration.DoesNotExist:
		return HttpResponse('You are not registered for this conference.')

	if not r.payconfirmedat:
		if r.regtype.cost != 0:
			return HttpResponse('You are not a confirmed attendee of this conference.')

	# Generate a list of all feedback:able sessions, meaning all sessions that have already started,
	# since you can't give feedback on something that does not yet exist.
	if is_conf_tester:
		sessions = ConferenceSession.objects.select_related().filter(conference=conference).filter(can_feedback=True).filter(status=1)
	else:
		sessions = ConferenceSession.objects.select_related().filter(conference=conference).filter(can_feedback=True).filter(starttime__lte=datetime.now()).filter(status=1)

	# Then get a list of everything this user has feedbacked on
	feedback = ConferenceSessionFeedback.objects.filter(conference=conference, attendee=request.user)

	# Since we can't trick django to do a LEFT JOIN for us here, implement that part
	# in code here. The number of sessions is always going to be low, so it won't
	# be too big a performance issue.
	for s in sessions:
		fb = [f for f in feedback if f.session==s]
		if len(fb):
			s.has_given_feedback = True

	return render_conference_response(request, conference, 'feedback', 'confreg/feedback_index.html', {
		'sessions': sessions,
		'is_tester': is_conf_tester,
	})

@login_required
def feedback_session(request, confname, sessionid):
	# Room for optimization: don't get these as separate steps
	conference = get_object_or_404(Conference, urlname=confname)
	session = get_object_or_404(ConferenceSession, pk=sessionid, conference=conference, status=1)

	if not conference.feedbackopen:
		# Allow conference testers to override
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'feedback', 'confreg/feedbackclosed.html')
		else:
			is_conf_tester = True
	else:
		is_conf_tester = False

	if session.starttime > datetime.now() and not is_conf_tester:
		return render_conference_response(request, conference, 'feedback', 'confreg/feedbacknotyet.html', {
			'session': session,
		})

	try:
		feedback = ConferenceSessionFeedback.objects.get(conference=conference, session=session, attendee=request.user)
	except ConferenceSessionFeedback.DoesNotExist:
		feedback = ConferenceSessionFeedback()

	if request.method=='POST':
		form = ConferenceSessionFeedbackForm(data=request.POST, instance=feedback)
		if form.is_valid():
			feedback = form.save(commit=False)
			feedback.conference = conference
			feedback.attendee = request.user
			feedback.session = session
			feedback.save()
			return HttpResponseRedirect('..')
	else:
		form = ConferenceSessionFeedbackForm(instance=feedback)

	return render_conference_response(request, conference, 'feedback', 'confreg/feedback.html', {
		'session': session,
		'form': form,
	})


@login_required
@transaction.atomic
def feedback_conference(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.feedbackopen:
		# Allow conference testers to override
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'feedback', 'confreg/feedbackclosed.html')

	# Get all questions
	questions = ConferenceFeedbackQuestion.objects.filter(conference=conference)

	# Get all current responses
	responses = ConferenceFeedbackAnswer.objects.filter(conference=conference, attendee=request.user)

	if request.method=='POST':
		form = ConferenceFeedbackForm(data=request.POST, questions=questions, responses=responses)
		if form.is_valid():
			# We've got the data, now write it to the database.
			for q in questions:
				a,created = ConferenceFeedbackAnswer.objects.get_or_create(conference=conference, question=q, attendee=request.user)
				if q.isfreetext:
					a.textanswer = form.cleaned_data['question_%s' % q.id]
				else:
					a.rateanswer = form.cleaned_data['question_%s' % q.id]
				a.save()
			return HttpResponseRedirect('..')
	else:
		form = ConferenceFeedbackForm(questions=questions, responses=responses)

	return render_conference_response(request, conference, 'feedback', 'confreg/feedback_conference.html', {
		'session': session,
		'form': form,
	})


class SessionSet(object):
	def __init__(self, allrooms, day_rooms, totalwidth, pixelsperminute, sessions):
		self.headersize = 30
		self.available_rooms = allrooms
		self.totalwidth = totalwidth
		self.pixelsperminute = pixelsperminute

		# Get a dict from each roomid to the 0-based position of the room from left to right,
		# so the position can be calculated.
		self.rooms = dict(zip(day_rooms, range(len(day_rooms))))

		# Populate the dict for all sessions
		self.sessions = [self._session_template_dict(s) for s in sessions if s['room_id'] or s['cross_schedule']]

	def _session_template_dict(self, s):
		# For old-style rendering, update positions
		if not s['cross_schedule']:
			s.update({
				'leftpos': self.roomwidth()*self.rooms[s['room_id']],
				'toppos': self.timediff_to_y_pixels(s['starttime'], s['firsttime'])+self.headersize,
				'widthpos': self.roomwidth()-2,
				'heightpos': self.timediff_to_y_pixels(s['endtime'], s['starttime']),
			})
		else:
			s.update({
				'leftpos': 0,
				'toppos': self.timediff_to_y_pixels(s['starttime'], s['firsttime'])+self.headersize,
				'widthpos': self.roomwidth() * len(self.rooms) - 2,
				'heightpos': self.timediff_to_y_pixels(s['endtime'], s['starttime'])-2,
			})
			if 'id' in s:
				del s['id']
		return s

	def all(self):
		return self.sessions

	def schedule_height(self):
		return self.timediff_to_y_pixels(self.sessions[0]['lasttime'], self.sessions[0]['firsttime'])+2+self.headersize

	def schedule_width(self):
		if len(self.rooms):
			return self.roomwidth()*len(self.rooms)
		else:
			return 0

	def roomwidth(self):
		if len(self.rooms):
			return int(self.totalwidth/len(self.rooms))
		else:
			return 0

	def timediff_to_y_pixels(self, t, compareto):
		return ((t - compareto).seconds/60)*self.pixelsperminute

	def allrooms(self):
		return [{
			'id': id,
			'name': self.available_rooms[id]['roomname'],
			'leftpos': self.roomwidth()*self.rooms[id],
			'widthpos': self.roomwidth()-2,
			'heightpos': self.headersize-2,
			'sessions': list(self.room_sessions(id)),
		} for id, idx in sorted(self.rooms.items(), key=lambda x: x[1])]

	def room_sessions(self, roomid):
		roomprevsess = None
		for s in self.sessions:
			if s['cross_schedule'] or s['room_id'] == roomid:
				if roomprevsess and roomprevsess['endtime'] < s['starttime']:
					yield {'empty': True,
						   'length': (s['starttime']-roomprevsess['endtime']).total_seconds()/60,
					}
				roomprevsess = s
				yield s


def _scheduledata(request, conference):
	tracks = exec_to_dict("SELECT id, color, incfp, trackname, sortkey FROM confreg_track t WHERE conference_id=%(confid)s AND EXISTS (SELECT 1 FROM confreg_conferencesession s WHERE s.conference_id=%(confid)s AND s.track_id=t.id AND s.status=1) ORDER BY sortkey", {
		'confid': conference.id,
	})

	allrooms = exec_to_keyed_dict("SELECT id, sortkey, roomname FROM confreg_room r WHERE conference_id=%(confid)s", {
		'confid': conference.id,
	})

	day_rooms = exec_to_keyed_dict("WITH t AS (SELECT DISTINCT s.starttime::date AS day, room_id FROM confreg_conferencesession s WHERE s.conference_id=%(confid)s AND status=1 AND s.room_id IS NOT NULL) SELECT day, array_agg(room_id ORDER BY r.sortkey, r.roomname) AS rooms FROM t INNER JOIN confreg_room r on r.id=t.room_id GROUP BY day", {
		'confid': conference.id,
	})

	raw = exec_to_grouped_dict("SELECT s.starttime::date AS day, s.id, s.starttime, s.endtime, to_json(t.*) AS track, s.track_id, to_json(r.*) AS room, s.room_id, s.title, to_char(starttime, 'HH24:MI') || ' - ' || to_char(endtime, 'HH24:MI') AS timeslot, extract(epoch FROM endtime-starttime)/60 AS length, min(starttime) OVER days AS firsttime, max(endtime) OVER days AS lasttime, cross_schedule, EXISTS (SELECT 1 FROM confreg_conferencesessionslides sl WHERE sl.session_id=s.id) AS has_slides, COALESCE(json_agg(json_build_object('id', spk.id, 'name', spk.fullname, 'company', spk.company, 'twittername', spk.twittername)) FILTER (WHERE spk.id IS NOT NULL), '[]') AS speakers FROM confreg_conferencesession s LEFT JOIN confreg_track t ON t.id=s.track_id LEFT JOIN confreg_room r ON r.id=s.room_id LEFT JOIN confreg_conferencesession_speaker css ON css.conferencesession_id=s.id LEFT JOIN confreg_speaker spk ON spk.id=css.speaker_id WHERE s.conference_id=%(confid)s AND s.status=1 AND (cross_schedule OR room_id IS NOT NULL) GROUP BY s.id, t.id, r.id WINDOW days AS (PARTITION BY s.starttime::date) ORDER BY day, s.starttime, r.sortkey", {
		'confid': conference.id,
	})

	days = []
	for d, sessions in raw.items():
		sessionset = SessionSet(allrooms, day_rooms[d]['rooms'],
								conference.schedulewidth, conference.pixelsperminute,
								sessions)
		days.append({
			'day': d,
			'sessions': list(sessionset.all()),
			'rooms': sessionset.allrooms(),
			'schedule_height': sessionset.schedule_height(),
			'schedule_width': sessionset.schedule_width(),
		})

	return {
		'days': days,
		'tracks': tracks,
	}

def schedule(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.scheduleactive:
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'schedule', 'confreg/scheduleclosed.html')


	return render_conference_response(request, conference, 'schedule', 'confreg/schedule.html', _scheduledata(request, conference))

def schedulejson(request, confname):
	conference = get_authenticated_conference(request, confname)

	return HttpResponse(json.dumps(_scheduledata(request, conference),
								   cls=JsonSerializer,
								   indent=2),
						content_type='application/json')

def sessionlist(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.sessionsactive:
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'sessions', 'confreg/sessionsclosed.html')

	sessions = ConferenceSession.objects.filter(conference=conference).filter(cross_schedule=False).filter(status=1).order_by('track__sortkey', 'track', 'title')
	return render_conference_response(request, conference, 'sessions', 'confreg/sessionlist.html', {
		'sessions': sessions,
	})

def schedule_ical(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.scheduleactive:
		# Not open. But we can't really render an error, so render a
		# completely empty session list instead
		sessions = None
	else:
		sessions = ConferenceSession.objects.filter(conference=conference).filter(cross_schedule=False).filter(status=1).filter(starttime__isnull=False).order_by('starttime')
	return render(request, 'confreg/schedule.ical', {
		'conference': conference,
		'sessions': sessions,
		'servername': request.META['SERVER_NAME'],
	}, content_type='text/calendar')

def session(request, confname, sessionid, junk=None):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.sessionsactive:
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'schedule', 'confreg/sessionsclosed.html')

	session = get_object_or_404(ConferenceSession, conference=conference, pk=sessionid, cross_schedule=False, status=1)
	return render_conference_response(request, conference, 'schedule', 'confreg/session.html', {
		'session': session,
		'slides': ConferenceSessionSlides.objects.filter(session=session),
	})

def session_slides(request, confname, sessionid, slideid):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.sessionsactive:
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'schedule', 'confreg/sessionsclosed.html')

	session = get_object_or_404(ConferenceSession, conference=conference, pk=sessionid, cross_schedule=False, status=1)
	slides = get_object_or_404(ConferenceSessionSlides, session=session, id=slideid)
	return HttpResponse(slides.content,
						content_type='application/pdf')

def speaker(request, confname, speakerid, junk=None):
	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.sessionsactive:
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'schedule', 'confreg/sessionsclosed.html')

	speaker = get_object_or_404(Speaker, pk=speakerid)
	sessions = ConferenceSession.objects.filter(conference=conference, speaker=speaker, cross_schedule=False, status=1).order_by('starttime')
	if len(sessions) < 1:
		raise Http404("Speaker has no sessions at this conference")
	return render_conference_response(request, conference, 'schedule', 'confreg/speaker.html', {
		'speaker': speaker,
		'sessions': sessions,
	})

def speakerphoto(request, speakerid):
	speakerphoto = get_object_or_404(Speaker_Photo, pk=speakerid)
	return HttpResponse(base64.b64decode(speakerphoto.photo), content_type='image/jpg')

@login_required
def speakerprofile(request, confurlname):
	conf = get_object_or_404(Conference, urlname=confurlname)
	speaker = conferences = callforpapers = None
	try:
		speaker = get_object_or_404(Speaker, user=request.user)
		conferences = Conference.objects.filter(conferencesession__speaker=speaker).distinct()
		callforpapers = Conference.objects.filter(callforpapersopen=True).order_by('startdate')
	except Speaker.DoesNotExist:
		speaker = None
		conferences = []
		callforpapers = None
	except Exception:
		pass

	if request.method=='POST':
		# Attempt to save
		# If this is a new speaker, create an instance for it
		if not speaker:
			speaker = Speaker(user=request.user, fullname=request.user.first_name)
			speaker.speakertoken = generate_random_token()
			speaker.save()

		form = SpeakerProfileForm(data=request.POST, files=request.FILES, instance=speaker)
		if form.is_valid():
			if request.FILES.has_key('photo'):
				raise Exception("Deal with the file!")
			form.save()
			return HttpResponseRedirect('.')
	else:
		form = SpeakerProfileForm(instance=speaker)

	return render_conference_response(request, conf, 'cfp', 'confreg/speakerprofile.html', {
			'speaker': speaker,
			'conferences': conferences,
			'callforpapers': callforpapers,
			'form': form,
	})

@login_required
@transaction.atomic
def callforpapers(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	# This is called both for open and non-open call for papers, to let submitters view
	# when the schedule is not published. Thus, no check for callforpapersopen here.

	is_tester = conference.testers.filter(pk=request.user.id).exists()

	try:
		speaker = Speaker.objects.get(user=request.user)
		sessions = ConferenceSession.objects.filter(conference=conference, speaker=speaker).order_by('title')
		other_submissions = ConferenceSession.objects.filter(speaker=speaker).exclude(conference=conference).exists()
	except Speaker.DoesNotExist:
		other_submissions = False
		sessions = []

	return render_conference_response(request, conference, 'cfp', 'confreg/callforpapers.html', {
			'other_submissions': other_submissions,
			'sessions': sessions,
			'is_tester': is_tester,
	})


@login_required
def callforpapers_edit(request, confname, sessionid):
	conference = get_object_or_404(Conference, urlname=confname)
	is_tester = conference.testers.filter(pk=request.user.id).exists()

	if sessionid == 'new':
		if not (conference.callforpapersopen or is_tester):
			# Should never happen, so just redirect the user
			return HttpResponseRedirect("../")

		# Create speaker record if necessary
		speaker, created = Speaker.objects.get_or_create(user=request.user, defaults={
			'fullname': request.user.first_name,
			'speakertoken': generate_random_token(),
		})

		session = ConferenceSession(conference=conference, status=0, initialsubmit=datetime.now())
	else:
		# Find users speaker record (should always exist when we get this far)
		speaker = get_object_or_404(Speaker, user=request.user)

		# Find the session record (should always exist when we get this far)
		session = get_object_or_404(ConferenceSession, conference=conference,
									speaker=speaker, pk=sessionid)

	# If the user is a tester, it overrides the callforpapersopen check
	isopen = conference.callforpapersopen or is_tester
	if (isopen and session.status != 0) or not isopen:
		# Anything that's not "open and in status submitted" renders
		# a view of the session instead of the actual session.
		# If there is feedback for this session available, render that
		# on the same page. If feedback is  still open, we show nothing
		feedback_fields = ('topic_importance', 'content_quality', 'speaker_knowledge', 'speaker_quality')
		if is_tester or not conference.feedbackopen:
			feedbackdata = [{'key': k, 'title': k.replace('_',' ').title(), 'num': [0]*5} for k in feedback_fields]
			feedbacktext = []
			fb = list(ConferenceSessionFeedback.objects.filter(conference=conference, session=session))
			feedbackcount = len(fb)
			for f in fb:
				# Summarize the values
				for d in feedbackdata:
					if getattr(f, d['key']) > 0:
						d['num'][getattr(f, d['key'])-1] += 1
				# Add the text if necessary
				if f.speaker_feedback:
					feedbacktext.append({
						'feedback': f.speaker_feedback,
						'scores': [getattr(f, fn) for fn in feedback_fields],
						})
			# Build the histogram data. For now, one query per measurement
			curs = connection.cursor()
			feedbackcomparisons = []
			for measurement in feedback_fields:
				curs.execute("SELECT g.g,g.g+0.25,COALESCE(y.count,0),this FROM generate_series(0,4.75,0.25) g(g) LEFT JOIN (SELECT r, count(*), max(this::int) AS this FROM (SELECT session_id,round(floor(avg({0})*4)/4,2) AS r,session_id=%(sessid)s AS this FROM confreg_conferencesessionfeedback WHERE conference_id=%(confid)s GROUP BY session_id) x GROUP BY r) y ON g.g=y.r".format(measurement), {
					'confid': conference.id,
					'sessid': session.id,
				})
				feedbackcomparisons.append({
					'key': measurement,
					'title': measurement.replace('_',' ').title(),
					'vals': curs.fetchall(),
				})
		else:
			feedbackcount = 0
			feedbackdata = None
			feedbacktext = None
			feedbackcomparisons = None

		# Slides slides slides!
		if request.method == 'POST':
			slidesurlform = SessionSlidesUrlForm(data=request.POST)
			slidesfileform = SessionSlidesFileForm(data=request.POST, files=request.FILES)
			if slidesurlform.is_valid() and slidesfileform.is_valid():
				# URL first!
				if slidesurlform.cleaned_data['url']:
					ConferenceSessionSlides(session=session,
											name=slidesurlform.cleaned_data['url'][:100],
											url=slidesurlform.cleaned_data['url'],
											content=None).save()
					return HttpResponseRedirect(".")
				elif request.FILES:
					if len(request.FILES) != 1:
						raise Exception("Only one file at a time, sorry!")
					for k,v in request.FILES.items():
						ConferenceSessionSlides(session=session,
												name=v.name,
												content=v.read()).save()
					return HttpResponseRedirect(".")
				else:
					# No url, no file, so just re-render
					pass
		else:
			slidesurlform = SessionSlidesUrlForm()
			slidesfileform = SessionSlidesFileForm()

		return render_conference_response(request, conference, 'cfp', 'confreg/session_feedback.html', {
			'session': session,
			'feedbackcount': feedbackcount,
			'feedbackdata': feedbackdata,
			'feedbacktext': feedbacktext,
			'feedbackcomparisons': feedbackcomparisons,
			'feedbackfields': [f.replace('_',' ').title() for f in feedback_fields],
			'slidesurlform': slidesurlform,
			'slidesfileform': slidesfileform,
			'slides': ConferenceSessionSlides.objects.filter(session=session),
			})

	SpeakerFormset = formsets.formset_factory(CallForPapersSpeakerForm, can_delete=True, extra=1)

	if sessionid != 'new':
		# Get all additional speakers (that means all speakers who isn't the current one)
		speaker_initialdata = [{'email': s.user.email} for s in session.speaker.exclude(user=request.user)]
	else:
		speaker_initialdata = None

	if request.method == 'POST':
		# Save it!
		form = CallForPapersForm(data=request.POST, instance=session)
		speaker_formset = SpeakerFormset(data=request.POST, initial=speaker_initialdata, prefix="extra_speakers")
		if form.is_valid() and speaker_formset.is_valid():
			form.save()
			# Explicitly add the submitter as a speaker
			session.speaker.add(speaker)

			if speaker_formset.has_changed():
				# Additional speaker either added or removed
				for f in speaker_formset:
					# There is at least one empty form at the end, so skip it
					if not getattr(f, 'cleaned_data', False): continue

					# Somehow we can end up with an unspecified email. Not sure how it can happen,
					# since the field is mandatory, but if it does just ignore it.
					if not 'email' in f.cleaned_data: continue

					# Speaker always exist, since the form has validated
					spk = Speaker.objects.get(user__email=f.cleaned_data['email'])

					if f.cleaned_data['DELETE']:
						session.speaker.remove(spk)
					else:
						session.speaker.add(spk)
			messages.info(request, "Your session '%s' has been saved!" % session.title)
			return HttpResponseRedirect("../")
	else:
		# GET --> render empty form
		form = CallForPapersForm(instance=session)
		speaker_formset = SpeakerFormset(initial=speaker_initialdata, prefix="extra_speakers")

	return render_conference_response(request, conference, 'cfp', 'confreg/callforpapersform.html', {
			'form': form,
			'speaker_formset': speaker_formset,
			'session': session,
	})

@login_required
@transaction.atomic
def callforpapers_copy(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	speaker = get_object_or_404(Speaker, user=request.user)

	if request.method == 'POST':
		form = CallForPapersCopyForm(conference, speaker, data=request.POST)
		if form.is_valid():
			for s in form.cleaned_data['sessions']:
				# The majority of all fields should just be blank in the new submission, so create
				# a new session object instead of trying to copy the old one.
				submissionnote = u"Submission copied from {0}.".format(s.conference)
				if s.submissionnote:
					submissionnote += " Original note:\n\n" + s.submissionnote

				n = ConferenceSession(conference=conference,
									  title=s.title,
									  abstract=s.abstract,
									  skill_level=s.skill_level,
									  status=0,
									  initialsubmit=datetime.now(),
									  submissionnote=submissionnote,
									  )
				n.save()
				n.speaker = s.speaker.all()
			return HttpResponseRedirect('../')
	else:
		form = CallForPapersCopyForm(conference, speaker)

	return render_conference_response(request, conference, 'cfp', 'confreg/callforpaperscopyform.html', {
		'form': form,
	})

@login_required
def callforpapers_delslides(request, confname, sessionid, slideid):
	conference = get_object_or_404(Conference, urlname=confname)
	speaker = get_object_or_404(Speaker, user=request.user)
	session = get_object_or_404(ConferenceSession, conference=conference,
								speaker=speaker, pk=sessionid)
	slide = get_object_or_404(ConferenceSessionSlides, session=session, id=slideid)
	slide.delete()
	return HttpResponseRedirect('../../')

@login_required
@transaction.atomic
def callforpapers_confirm(request, confname, sessionid):
	conference = get_object_or_404(Conference, urlname=confname)

	# Find users speaker record (should always exist when we get this far)
	speaker = get_object_or_404(Speaker, user=request.user)

	# Find the session record (should always exist when we get this far)
	session = get_object_or_404(ConferenceSession, conference=conference,
								speaker=speaker, pk=sessionid)

	if session.status != 3 and session.status != 1:
		# Session needs to be either pending approval (render the form) or
		# already approved (indicate that it is). For any other status,
		# just send back to the index page.
		return HttpResponseRedirect("../..")

	if session.status == 1:
		# Confirmed
		return render_conference_response(request, conference, 'cfp', 'confreg/callforpapersconfirmed.html', {
		'session': session,
	})

	if request.method == 'POST':
		if request.POST.has_key('is_confirmed') and request.POST['is_confirmed'] == '1':
			session.status = 1 # Now approved!
			session.save()
			# We can generate the email for this right away, so let's do that
			for spk in session.speaker.all():
				send_template_mail(conference.contactaddr,
								   spk.user.email,
								   "Your session '%s' submitted to %s" % (session.title, conference),
								   'confreg/mail/session_notify.txt',
								   {
									 'conference': conference,
									 'session': session,
								   },
								   sendername = conference.conferencename,
								   receivername = spk.fullname,
							   )
			session.lastnotifiedstatus = 1 # Now also approved
			session.lastnotifiedtime = datetime.now()
			session.save()
			return HttpResponseRedirect(".")

	return render_conference_response(request, conference, 'cfp', 'confreg/callforpapersconfirm.html', {
		'session': session,
	})

@login_required
@transaction.atomic
def confirmreg(request, confname):
	# Confirm a registration step. This will show the user the final
	# cost of the registration, minus any discounts found (including
	# complete-registration vouchers).
	conference = get_object_or_404(Conference, urlname=confname)
	reg = get_object_or_404(ConferenceRegistration, attendee=request.user, conference=conference)
	# This should never happen since we should error out in the form,
	# but make sure we don't accidentally proceed.
	if not reg.regtype:
		return render_conference_response(request, conference, 'reg', 'confreg/noregtype.html')
	if reg.bulkpayment:
		return render_conference_response(request, conference, 'reg', 'confreg/bulkpayexists.html')

	registration_warnings = []

	# If there is already an invoice, then this registration has
	# been processed already.
	if reg.invoice:
		return HttpResponseRedirect("/events/%s/register/" % conference.urlname)

	# See if the registration type blocks it
	s = confirm_special_reg_type(reg.regtype.specialtype, reg)
	if s:
		return render_conference_response(request, conference, 'reg', 'confreg/specialregtypeconfirm.html', {
			'reason': s,
			})


	# Is this registration already on the waitlist?
	if hasattr(reg, 'registrationwaitlistentry'):
		if reg.registrationwaitlistentry.offeredon:
			# Waitlist has been offered, but has it expired?
			if reg.registrationwaitlistentry.offerexpires < datetime.now():
				# It has expired
				RegistrationWaitlistHistory(waitlist=reg.registrationwaitlistentry,
											text="Offer expired at {0}".format(reg.registrationwaitlistentry.offerexpires)).save()

				reg.registrationwaitlistentry.offeredon = None
				reg.registrationwaitlistentry.offerexpires = None
				# Move registration to the back of the waitlist
				reg.registrationwaitlistentry.enteredon = datetime.now()
				reg.registrationwaitlistentry.save()

				messages.warning(request, "We're sorry, but your registration was not completed in time before the offer expired, and has been moved back to the waitlist.")

				send_simple_mail(reg.conference.contactaddr,
								 reg.conference.contactaddr,
								 'Waitlist expired',
								 u'User {0} {1} <{2}> did not complete the registration before the waitlist offer expired.'.format(reg.firstname, reg.lastname, reg.email),
								 sendername=reg.conference.conferencename)

				return render_conference_response(request, conference, 'reg', 'confreg/waitlist_status.html', {
					'reg': reg,
				})
			else:
				# Offer has not expired, so fall through to below and actually
				# render the form.
				pass
		else:
			# Waitlist has not been offered, but the user is on it
			return render_conference_response(request, conference, 'reg', 'confreg/waitlist_status.html', {
				'reg': reg,
				})
	else:
		# Registration is not on the waitlist, but should it be? Count
		# Check if we do it at all...
		if conference.waitlist_active():
			return render_conference_response(request, conference, 'reg',
											  'confreg/offer_waitlist.html', {
												  'reg': reg,
											  })

	phone_error = errors = False

	if request.method == 'POST':
		if request.POST['submit'].find('Back') >= 0:
			return HttpResponseRedirect("../")
		if reg.regtype.require_phone:
			reg.phone = request.POST['phone']
			if len(reg.phone) < 3:
				phone_error = True
				errors = True

		if request.POST['submit'] == 'Confirm and finish' and not errors:
			# Get the invoice rows and flag any vouchers as used
			# (committed at the end of the view so if something
			# goes wrong they automatically go back to unused)
			try:
				invoicerows = invoicerows_for_registration(reg, True)
			except InvoicerowsException:
				# This Should Never Happen (TM) due to validations,
				# so just redirect back to the page for retry.
				return HttpResponseRedirect("../")

			totalcost = sum([r[2]*(1+(r[3] and r[3].vatpercent or 0)/Decimal(100.0)) for r in invoicerows])

			if len(invoicerows) <= 0:
				return HttpResponseRedirect("../")

			if totalcost == 0:
				# Paid in total with vouchers, or completely free
				# registration type. So just flag the registration
				# as confirmed.
				reg.payconfirmedat = datetime.now()
				reg.payconfirmedby = "no payment reqd"
				reg.save()
				notify_reg_confirmed(reg)
				return HttpResponseRedirect("../")

			# Else there is a cost, so we create an invoice for that
			# cost. Registration will be confirmed when the invoice is paid.
			manager = InvoiceManager()
			processor = InvoiceProcessor.objects.get(processorname="confreg processor")

			# Figure out when to autocancel this invoice, if at all.
			autocancel = get_invoice_autocancel(conference.invoice_autocancel_hours,
												reg.regtype.invoice_autocancel_hours,
												*[a.invoice_autocancel_hours for a in reg.additionaloptions.filter(invoice_autocancel_hours__isnull=False)])
			if hasattr(reg, 'registrationwaitlistentry'):
				# We're on the waitlist. We've already checked that this is
				# OK, but this value might control how long the invoice is
				# available.
				if autocancel is None or reg.registrationwaitlistentry.offerexpires < autocancel:
					autocancel = reg.registrationwaitlistentry.offerexpires

			reg.invoice = manager.create_invoice(
				request.user,
				request.user.email,
				reg.firstname + ' ' + reg.lastname,
				reg.company + "\n" + reg.address + "\n" + reg.country.name,
				"%s registration for %s" % (conference.conferencename, reg.email),
				datetime.now(),
				datetime.now(),
				invoicerows,
				processor = processor,
				processorid = reg.pk,
				bankinfo = False,
				accounting_account = settings.ACCOUNTING_CONFREG_ACCOUNT,
				accounting_object = conference.accounting_object,
				canceltime = autocancel,
			)

			reg.invoice.save()
			reg.save()
			return HttpResponseRedirect("../invoice/%s/" % reg.pk)

		# Else this is some random button we haven't heard of, so just
		# fall through and show the form again.

	# Figure out what should go on the invoice. Don't flag possible
	# vouchers as used, since confirmation isn't done yet.
	try:
		invoicerows = invoicerows_for_registration(reg, False)
	except InvoicerowsException:
		# This should not be possible because of previous validations,
		# so if it does just redirect back for retry.
		return HttpResponseRedirect("../")

	for r in invoicerows:
		# Calculate the with-vat information for this row
		if r[3]:
			r.append(r[2]*(100+r[3].vatpercent)/Decimal(100))
		else:
			r.append(r[2])

	totalcost = sum([r[2] for r in invoicerows])
	totalwithvat = sum([r[4] for r in invoicerows])

	# It should be impossible to end up with zero invoice rows, so just
	# redirect back if that happens
	if len(invoicerows) <= 0:
		return HttpResponseRedirect("../")

	# Add warnings for mismatching name
	if reg.firstname != request.user.first_name or reg.lastname != request.user.last_name:
		registration_warnings.append(u"Registration name ({0} {1}) does not match account name ({2} {3}). Please make sure that this is correct, and that you are <strong>not</strong> registering using a different account than your own, as access to the account may be needed during the event!".format(reg.firstname, reg.lastname, request.user.first_name, request.user.last_name))


	return render_conference_response(request, conference, 'reg', 'confreg/regform_confirm.html', {
		'reg': reg,
		'invoicerows': invoicerows,
		'totalcost': totalcost,
		'totalwithvat': totalwithvat,
		'regalert': reg.regtype.alertmessage,
		'warnings': registration_warnings,
		'phone': reg.phone,
		'phone_error': phone_error,
		})


@login_required
@transaction.atomic
def waitlist_signup(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	reg = get_object_or_404(ConferenceRegistration, attendee=request.user, conference=conference)

	# CSRF ensures that this post comes from us.
	if request.POST['submit'] != 'Sign up on waitlist':
		raise Exception("Invalid post button")
	if not request.POST.has_key('confirm') or request.POST['confirm'] != '1':
		messages.warning(request, "You must check the box to confirm signing up on the waitlist")
		return HttpResponseRedirect("../confirm/")

	if hasattr(reg, 'registrationwaitlistentry'):
		raise Exception("This registration is already on the waitlist")

	# Ok, so put this registration on the waitlist
	waitlist = RegistrationWaitlistEntry(registration=reg)
	waitlist.save()

	RegistrationWaitlistHistory(waitlist=waitlist, text="Signed up for waitlist").save()

	# Notify the conference organizers
	send_simple_mail(reg.conference.contactaddr,
					 reg.conference.contactaddr,
					 'Waitlist signup',
					 u'User {0} {1} <{2}> signed up for the waitlist.'.format(reg.firstname, reg.lastname, reg.email),
					 sendername=reg.conference.conferencename)

	# Once on the waitlist, redirect back to the registration form page
	# which will show the waitlist information.
	return HttpResponseRedirect("../confirm/")

@login_required
@transaction.atomic
def waitlist_cancel(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	reg = get_object_or_404(ConferenceRegistration, attendee=request.user, conference=conference)

	# CSRF ensures that this post comes from us.
	if request.POST['submit'] != 'Cancel waitlist':
		raise Exception("Invalid post button")
	if not request.POST.has_key('confirm') or request.POST['confirm'] != '1':
		messages.warning(request, "You must check the box to confirm canceling your position on the waitlist.")
		return HttpResponseRedirect("../confirm/")

	if not hasattr(reg, 'registrationwaitlistentry'):
		raise Exception("This registration is not on the waitlist")

	reg.registrationwaitlistentry.delete()

	# Notify the conference organizers
	send_simple_mail(reg.conference.contactaddr,
					 reg.conference.contactaddr,
					 'Waitlist cancel',
					 u'User {0} {1} <{2}> canceled from the waitlist.'.format(reg.firstname, reg.lastname, reg.email),
					 sendername=reg.conference.conferencename)

	messages.info(request, "Your registration has been removed from the waitlist. You may re-enter it if you change your mind.")

	# Once on the waitlist, redirect back to the registration form page
	# which will show the waitlist information.
	return HttpResponseRedirect("../confirm/")

@login_required
def cancelreg(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	return render_conference_response(request, conference, 'reg', 'confreg/canceled.html')

@login_required
@transaction.atomic
def invoice(request, confname, regid):
	# Show the invoice. We do this in a separate view from the main view,
	# even though the invoice is present on the main view as well, in order
	# to make things even more obvious.
	# Assumes that the actual invoice has already been created!
	conference = get_object_or_404(Conference, urlname=confname)
	reg = get_object_or_404(ConferenceRegistration, id=regid, attendee=request.user, conference=conference)

	if reg.bulkpayment:
		return render_conference_response(request, conference, 'reg', 'confreg/bulkpayexists.html')

	if not reg.invoice:
		# We should never get here if we don't have an invoice. If it does
		# happen, just redirect back.
		return HttpResponseRedirect('../../')

	if reg.invoice.canceltime and reg.invoice.canceltime < datetime.now() and not reg.payconfirmedat:
		# Yup, should be canceled
		manager = InvoiceManager()
		manager.cancel_invoice(reg.invoice,
							   "Invoice was automatically canceled because payment was not received on time.")
		return HttpResponseRedirect('../../')

	return render_conference_response(request, conference, 'reg', 'confreg/invoice.html', {
			'reg': reg,
			'invoice': InvoicePresentationWrapper(reg.invoice, "%s/events/%s/register/" % (settings.SITEBASE, conference.urlname)),
			})

@login_required
@transaction.atomic
def invoice_cancel(request, confname, regid):
	# Show an optional cancel of this invoice
	conference = get_object_or_404(Conference, urlname=confname)
	reg = get_object_or_404(ConferenceRegistration, id=regid, attendee=request.user, conference=conference)

	if not reg.invoice:
		# We should never get here if we don't have an invoice. If it does
		# happen, just redirect back.
		return HttpResponseRedirect('../../../')
	if reg.payconfirmedat:
		# If the invoice is already paid while we were waiting, don't allow
		# cancellation any more.
		return HttpResponseRedirect('../../../')

	if request.method == 'POST':
		if request.POST['submit'].find('Cancel invoice') >= 0:
			manager = InvoiceManager()
			manager.cancel_invoice(reg.invoice, u"User {0} requested cancellation".format(request.user))
			return HttpResponseRedirect('../../../')
		else:
			return HttpResponseRedirect('../')

	return render_conference_response(request, conference, 'reg', 'confreg/invoicecancel.html', {
		'reg': reg,
	})

@login_required
def attendee_mail(request, confname, mailid):
	conference = get_object_or_404(Conference, urlname=confname)
	reg = get_object_or_404(ConferenceRegistration, attendee=request.user, conference=conference)

	mail = get_object_or_404(AttendeeMail, conference=conference, pk=mailid, regclasses=reg.regtype.regclass)

	return render_conference_response(request, conference, 'reg', 'confreg/attendee_mail_view.html', {
		'conference': conference,
		'mail': mail,
		})

@transaction.atomic
def optout(request, token=None):
	if token:
		try:
			reg = ConferenceRegistration.objects.get(regtoken=token)
			userid = reg.attendee_id
			email = reg.email
		except ConferenceRegistration.DoesNotExist:
			try:
				speaker = Speaker.objects.get(speakertoken=token)
				userid = speaker.user_id
				email = speaker.user.email
			except Speaker.DoesNotExist:
				raise Http404("Token not found")
	else:
		# No token, so require login
		if not request.user.is_authenticated:
			return HttpResponseRedirect('%s?next=%s' % (settings.LOGIN_URL, request.path))
		userid = request.user.id
		email = request.user.email

	if request.method == 'POST':
		global_optout = request.POST.get('global', '0')=='1'
		sids = exec_to_list("SELECT id FROM confreg_conferenceseries")
		optout_ids = [i for i, in sids if request.POST.get('series_{0}'.format(i), '0') == '1']

		if global_optout:
			exec_no_result('INSERT INTO confreg_globaloptout (user_id) VALUES (%(u)s) ON CONFLICT DO NOTHING', {'u': userid})
		else:
			exec_no_result('DELETE FROM confreg_globaloptout WHERE user_id=%(u)s', {'u': userid})

		exec_no_result('DELETE FROM confreg_conferenceseriesoptout WHERE user_id=%(u)s AND NOT series_id=ANY(%(series)s)',{
			'u': userid,
			'series': optout_ids,
		})
		exec_no_result('INSERT INTO confreg_conferenceseriesoptout (series_id, user_id) SELECT s, %(u)s FROM UNNEST(%(series)s::int[]) s(s) WHERE NOT EXISTS (SELECT 1 FROM confreg_conferenceseriesoptout o WHERE o.user_id=%(u)s AND o.series_id=s.s) ON CONFLICT DO NOTHING', {
			'u': userid,
			'series': optout_ids,
		})
		return HttpResponse("Your conference opt-out settings have been updated.")

	series = exec_to_dict("SELECT s.id, s.name, oo IS NOT NULL AS optout FROM confreg_conferenceseries s LEFT JOIN confreg_conferenceseriesoptout oo ON oo.series_id=s.id AND oo.user_id=%(userid)s", {
		'userid': userid,
	})

	return render(request, 'confreg/optout.html', {
		'email': email,
		'globaloptout': GlobalOptOut.objects.filter(user=userid).exists(),
		'series': series,
	})

@transaction.atomic
def createvouchers(request, confname):
	conference = get_authenticated_conference(request, confname)

	# Creation of pre-paid vouchers for conference registrations
	if request.method == 'POST':
		form = PrepaidCreateForm(conference, data=request.POST)
		if form.is_valid():
			# All data is correct, create the vouchers
			# (by first creating a batch)

			regtype = RegistrationType.objects.get(pk=form.data['regtype'], conference=conference)
			regcount = int(form.data['count'])
			buyer = User.objects.get(pk=form.data['buyer'])
			buyername = u'{0} {1}'.format(buyer.first_name, buyer.last_name)

			batch = PrepaidBatch(conference=conference,
								 regtype=regtype,
								 buyer=buyer,
								 buyername=buyername)
			batch.save()

			for n in range(0, regcount):
				v = PrepaidVoucher(conference=conference,
								   vouchervalue=base64.b64encode(os.urandom(37)).rstrip('='),
								   batch=batch)
				v.save()

			if form.data.has_key('invoice') and form.data['invoice']:
				invoice = Invoice(recipient_user=buyer,
								  recipient_email=buyer.email,
								  recipient_name=buyername,
								  title='%s prepaid vouchers' % conference.conferencename,
								  invoicedate=datetime.now(),
								  duedate=datetime.now(),
								  finalized=False,
								  total_amount=-1,
								  bankinfo=False,
								  accounting_account=settings.ACCOUNTING_CONFREG_ACCOUNT,
								  accounting_object = conference.accounting_object,
							  )
				invoice.save()
				invoice.invoicerow_set.add(InvoiceRow(invoice=invoice,
													  rowtext='Voucher for "%s"' % regtype.regtype,
													  rowcount=regcount,
													  rowamount=regtype.cost,
													  vatrate=conference.vat_registrations,
				), bulk=False)
				invoice.allowedmethods = InvoicePaymentMethod.objects.filter(auto=True)
				invoice.save()
				messages.warning(request, "Invoice created for this batch, but NOT finalized. Go do that manually!")
			return HttpResponseRedirect('%s/' % batch.id)
		# Else fall through to re-render
	else:
		# Get request means we render an empty form
		form = PrepaidCreateForm(conference)

	return render(request, 'confreg/prepaid_create_form.html', {
		'form': form,
		'conference': conference,
		'breadcrumbs': (('/events/admin/{0}/prepaid/list/'.format(conference.urlname), 'Prepaid vouchers'),),
	})

def listvouchers(request, confname):
	conference = get_authenticated_conference(request, confname)

	batches = PrepaidBatch.objects.select_related('regtype').filter(conference=conference).prefetch_related('prepaidvoucher_set')

	return render(request, 'confreg/prepaid_list.html', {
		'conference': conference,
		'batches': batches,
		'helplink': 'vouchers',
	})

def viewvouchers(request, confname, batchid):
	conference = get_authenticated_conference(request, confname)

	batch = get_object_or_404(PrepaidBatch, conference=conference, pk=batchid)
	vouchers = batch.prepaidvoucher_set.all()

	vouchermailtext = template_to_string('confreg/mail/prepaid_vouchers.txt',{
		'batch': batch,
		'vouchers': vouchers,
		'conference': conference,
		})

	return render(request, 'confreg/prepaid_create_list.html', {
		'conference': conference,
		'batch': batch,
		'vouchers': vouchers,
		'vouchermailtext': vouchermailtext,
		'breadcrumbs': (('/events/admin/{0}/prepaid/list/'.format(conference.urlname), 'Prepaid vouchers'),),
		'helplink': 'vouchers',
	})

@transaction.atomic
def delvouchers(request, confname, batchid, voucherid):
	conference = get_authenticated_conference(request, confname)

	batch = get_object_or_404(PrepaidBatch, conference=conference, pk=batchid)
	voucher = get_object_or_404(PrepaidVoucher, batch=batch, pk=voucherid)

	if voucher.user or voucher.usedate:
		messages.error(request, "Unable to delete voucher, it has been used!")
	else:
		# OK, delete the voucher
		vcode = voucher.vouchervalue
		voucher.delete()
		messages.info(request, "Voucher {0} deleted.".format(vcode))
		if not batch.prepaidvoucher_set.exists():
			# Nothing left, so delete the batch
			batch.delete()
			messages.info(request, "Batch {0} now empty, so also deleted.".format(batchid))

	return HttpResponseRedirect('/events/admin/{0}/prepaid/list/'.format(confname))

@login_required
def viewvouchers_user(request, confname, batchid):
	conference = get_object_or_404(Conference, urlname=confname)
	batch = get_object_or_404(PrepaidBatch, conference=conference, pk=batchid)
	if batch.buyer != request.user:
		raise Http404()
	vouchers = batch.prepaidvoucher_set.all()

	return render_conference_response(request, conference, 'reg', 'confreg/prepaid_list.html', {
		'batch': batch,
		'vouchers': vouchers,
	})

def emailvouchers(request, confname, batchid):
	conference = get_authenticated_conference(request, confname)

	batch = PrepaidBatch.objects.get(pk=batchid)
	vouchers = batch.prepaidvoucher_set.all()

	send_template_mail(batch.conference.contactaddr,
					   batch.buyer.email,
					   "Attendee vouchers for %s" % batch.conference,
					   'confreg/mail/prepaid_vouchers.txt',
					   {
						   'batch': batch,
						   'vouchers': vouchers,
						   'conference': conference,
					   },
					   sendername=batch.conference.conferencename,
					   receivername=u"{0} {1}".format(batch.buyer.first_name, batch.buyer.last_name),
				   )
	return HttpResponse('OK')

@login_required
@transaction.atomic
def bulkpay(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	bulkpayments = BulkPayment.objects.filter(conference=conference, user=request.user)

	if conference.waitlist_active():
		return render_conference_response(request, conference, 'reg', 'confreg/bulkpay_list.html', {
			'activewaitlist': True,
			'bulkpayments': bulkpayments,
			'currency_symbol': settings.CURRENCY_SYMBOL.decode('utf8'),
		})

	if request.method == 'POST':
		confirmstep = (request.POST['submit'] == 'Confirm above registrations and generate invoice')
		form = BulkRegistrationForm(data=request.POST)
		email_list = request.POST['email_list']
		emails = [e for e in email_list.splitlines(False) if e]
		# Try to find registrations for all emails. We do this in an ugly loop
		# since I can't convince the django ORM to be smart enough. But this
		# is a very uncommon operation...
		state = []
		errors = not form.is_valid()
		totalcost = 0
		invoicerows = []
		allregs = []

		# Set up a savepoint for rolling back the counter of discount codes if necessary
		if confirmstep:
			savepoint = transaction.savepoint()

		for e in sorted(emails):
			regs = ConferenceRegistration.objects.filter(conference=conference, email__iexact=e)
			if len(regs) == 1:
				allregs.append(regs[0])
			else:
				state.append({'email': e, 'found': 0, 'text': 'Email not found or registration already completed.'})
				errors=1

		# Validate each entry
		for r in allregs:
			e = r.email

			if r.payconfirmedat:
				state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'Email not found or registration already completed.'})
				errors=1
			elif r.invoice:
				state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'This registration already has an invoice generated for individual payment.'})
				errors=1
			elif r.bulkpayment:
				state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'This registration is already part of a different bulk registration.'})
				errors=1
			elif not (r.regtype and r.regtype.active):
				state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'Registration type for this registration is not active!'})
				errors=1
			else:
				# If this is the confirmation step, we flag vouchers as used.
				# Else we just get the data and generate a confirmation page
				try:
					regrows = invoicerows_for_registration(r, confirmstep)
					s = sum([r[1]*r[2] for r in regrows])
					if s == 0:
						# No payment needed
						state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'Registration does not need payment'})
						errors=1
					else:
						# All content is valid, so just append it
						state.append({'email': regs[0].email, 'found': 1, 'pay': 1, 'total': s, 'rows':[u'%s (%s%s)' % (r[0], settings.CURRENCY_SYMBOL.decode('utf8'), r[2]) for r in regrows]})
						totalcost += s
						invoicerows.extend(regrows)

				except InvoicerowsException, ex:
					state.append({'email': e, 'found': 1, 'pay': 0, 'text': unicode(ex)})
					errors = 1

		if confirmstep:
			# Trying to finish things off, are we? :)
			if not errors:
				# Verify the total cost
				if Decimal(request.POST['confirmed_total_cost']) != totalcost:
					messages.warning(request, 'Total cost changed, probably because somebody modified their registration during processing. Please verify the costs below, and retry.')
					transaction.savepoint_rollback(savepoint)
				else:
					# Ok, actually generate an invoice for this one.
					# Create a bulk payment record
					bp = _create_and_assign_bulk_payment(request.user,
														 conference,
														 allregs,
														 invoicerows,
														 form.data['recipient_name'],
														 form.data['recipient_address'],
														 True)
					return HttpResponseRedirect('%s/' % bp.pk)
			else:
				messages.warning(request, 'An error occurred processing the registrations, please review the email addresses on the list')
				transaction.savepoint_rollback(savepoint)

		return render_conference_response(request, conference, 'reg', 'confreg/bulkpay_list.html', {
			'form': form,
			'email_list': email_list,
			'errors': errors,
			'totalcost': errors and -1 or totalcost,
			'state': state,
			'bulkpayments': bulkpayments,
			'currency_symbol': settings.CURRENCY_SYMBOL.decode('utf8'),
		})
	else:
		form = BulkRegistrationForm()
		return render_conference_response(request, conference, 'reg', 'confreg/bulkpay_list.html', {
			'form': form,
			'bulkpayments': bulkpayments,
			'currency_symbol': settings.CURRENCY_SYMBOL.decode('utf8'),
		})


@login_required
def bulkpay_view(request, confname, bulkpayid):
	conference = get_object_or_404(Conference, urlname=confname)

	bulkpayment = get_object_or_404(BulkPayment, conference=conference, user=request.user, pk=bulkpayid)

	return render_conference_response(request, conference, 'reg', 'confreg/bulkpay_view.html', {
		'bulkpayment': bulkpayment,
		'invoice': InvoicePresentationWrapper(bulkpayment.invoice, '.'),
	})


@login_required
@transaction.atomic
def talkvote(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.talkvoters.filter(pk=request.user.id) and not conference.administrators.filter(pk=request.user.id):
		return HttpResponse('You are not a talk voter for this conference!')

	isvoter = conference.talkvoters.filter(pk=request.user.id).exists()
	isadmin = conference.administrators.filter(pk=request.user.id).exists()

	alltracks = [{'id': t.id, 'trackname': t.trackname} for t in Track.objects.filter(conference=conference)]
	alltracks.insert(0, {'id': 0, 'trackname': 'No track'})
	alltrackids = [t['id'] for t in alltracks]
	selectedtracks = [int(id) for id in request.GET.getlist('tracks') if int(id) in alltrackids]
	allstatusids = [id for id,status in STATUS_CHOICES]
	selectedstatuses = [int(id) for id in request.GET.getlist('statuses') if int(id) in allstatusids]
	if selectedtracks:
		urltrackfilter = "{0}&".format("&".join(["tracks={0}".format(t) for t in selectedtracks]))
	else:
		selectedtracks = alltrackids
		urltrackfilter = ''

	if selectedstatuses:
		urlstatusfilter = "{0}&".format("&".join(["statuses={0}".format(t) for t in selectedstatuses]))
	else:
		selectedstatuses = allstatusids
		urlstatusfilter = ''

	curs = connection.cursor()

	order = ""
	if request.GET.has_key("sort"):
		if request.GET["sort"] == "avg":
			order = "avg DESC NULLS LAST,"
		elif request.GET["sort"] == "speakers":
			order = "speakers_full,"

	# Render the form. Need to do this with a manual query, can't figure
	# out the right way to do it with the django ORM.
	curs.execute("SELECT s.id, s.title, s.status, s.lastnotifiedstatus, s.abstract, s.submissionnote, (SELECT string_agg(spk.fullname, ',') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers, (SELECT string_agg(spk.fullname || '(' || spk.company || ')', ',') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers_full, (SELECT string_agg('####' ||spk.fullname || '\n' || spk.abstract, '\n\n') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers_long, u.username, v.vote, v.comment, avg(v.vote) OVER (PARTITION BY s.id)::numeric(3,2) AS avg, trackname FROM (confreg_conferencesession s CROSS JOIN auth_user u) LEFT JOIN confreg_track track ON track.id=s.track_id LEFT JOIN confreg_conferencesessionvote v ON v.session_id=s.id AND v.voter_id=u.id WHERE s.conference_id=%(confid)s AND u.id IN (SELECT user_id FROM confreg_conference_talkvoters tv WHERE tv.conference_id=%(confid)s) AND (COALESCE(s.track_id,0)=ANY(%(tracks)s)) AND status=ANY(%(statuses)s) ORDER BY " + order + "s.title,s.id, u.id=%(userid)s DESC, u.username", {
			'confid': conference.id,
			'userid': request.user.id,
			'tracks': selectedtracks,
			'statuses': selectedstatuses,
			})

	def getusernames(all):
		if not all:
			return

		firstid = all[0][0]
		for id, title, status, laststatus, abstract, submissionnote, speakers, speakers_full, speakers_long, username, vote, comment, avgvote, track in all:
			if id != firstid:
				return
			yield username

	def transform(all):
		if not all:
			return

		lastid = -1
		rd = {}
		for id, title, status, laststatus, abstract, submissionnote, speakers, speakers_full, speakers_long, username, vote, comment, avgvote, track in all:
			if id != lastid:
				if lastid != -1:
					yield rd
				rd = {
					'id': id,
					'title': title,
					'statusid': status,
					'status': get_status_string(status),
					'laststatusid': laststatus,
					'abstract': abstract,
					'submissionnote': submissionnote,
					'speakers': speakers,
					'speakers_full': speakers_full,
					'speakers_long': speakers_long,
					'avg': avgvote,
					'users': [],
					'comments': '',
					'owncomment': '',
					'track': track,
					}
				lastid = id
			rd['users'].append(vote)
			if comment:
				if username == request.user.username:
					rd['owncomment'] = comment
				else:
					rd['comments'] += "%s: %s<br/>" % (username, comment)

		yield rd

	all = curs.fetchall()
	return render(request, 'confreg/sessionvotes.html', {
			'users': getusernames(all),
			'sessionvotes': transform(all),
			'conference': conference,
			'isvoter': isvoter,
			'isadmin': isadmin,
		    'status_choices': STATUS_CHOICES,
		    'tracks': alltracks,
		    'selectedtracks': selectedtracks,
			'selectedstatuses': selectedstatuses,
		    'urlfilter': urltrackfilter + urlstatusfilter,
			'helplink': 'callforpapers',
			})

@login_required
@transaction.atomic
def talkvote_status(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.talkvoters.filter(pk=request.user.id) and not conference.administrators.filter(pk=request.user.id):
		return HttpResponse('You are not a talk voter for this conference!')

	isadmin = conference.administrators.filter(pk=request.user.id).exists()
	if not isadmin:
		return HttpResponse('Only admins can change the status')

	if request.method!='POST':
		return HttpResponse('Can only use POST')

	session = get_object_or_404(ConferenceSession, conference=conference, id=request.POST['sessionid'])
	session.status = int(request.POST['newstatus'])
	session.save()
	return HttpResponse("{0};{1}".format(get_status_string(session.status),
										 session.status!=session.lastnotifiedstatus and 1 or 0,
									 ),	content_type='text/plain')

@login_required
@transaction.atomic
def talkvote_vote(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.talkvoters.filter(pk=request.user.id):
		return HttpResponse('You are not a talk voter for this conference!')
	if request.method!='POST':
		return HttpResponse('Can only use POST')

	session = get_object_or_404(ConferenceSession, conference=conference, id=request.POST['sessionid'])
	v = int(request.POST['vote'])
	if v > 0:
		vote,created = ConferenceSessionVote.objects.get_or_create(session=session, voter=request.user)
		vote.vote = v
		vote.save()
	else:
		ConferenceSessionVote.objects.filter(session=session, voter=request.user).delete()

	# Re-calculate the average
	avg = session.conferencesessionvote_set.all().aggregate(Avg('vote'))['vote__avg']
	if avg is None:
		avg = 0
	return HttpResponse("{0:.2f}".format(avg), content_type='text/plain')

@login_required
@transaction.atomic
def talkvote_comment(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.talkvoters.filter(pk=request.user.id):
		return HttpResponse('You are not a talk voter for this conference!')
	if request.method!='POST':
		return HttpResponse('Can only use POST')

	session = get_object_or_404(ConferenceSession, conference=conference, id=request.POST['sessionid'])
	vote,created = ConferenceSessionVote.objects.get_or_create(session=session, voter=request.user)
	vote.comment = request.POST['comment']
	vote.save()

	return HttpResponse(vote.comment, content_type='text/plain')

@login_required
@csrf_exempt
@transaction.atomic
def createschedule(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	is_admin = conference.administrators.filter(pk=request.user.id).exists()
	if not (request.user.is_superuser or is_admin or
			conference.talkvoters.filter(pk=request.user.id).exists()
			):
		raise Http404('You are not an administrator or talk voter for this conference!')


	if request.method=="POST":
		if request.POST.has_key('get'):
			# Get the current list of tentatively scheduled talks
			s = {}
			for sess in conference.conferencesession_set.all():
				if sess.tentativeroom != None and sess.tentativescheduleslot != None:
					s['slot%s' % ((sess.tentativeroom.id * 1000000) + sess.tentativescheduleslot.id)] = 'sess%s' % sess.id
			return HttpResponse(json.dumps(s), content_type="application/json")

		# Else we are saving. This is only allowed by superusers and administrators,
		# not all talk voters (as it potentially changes the website).
		if not request.user.is_superuser and not is_admin:
			raise Http404('Only administrators can save!')

		# Remove all the existing mappings, and add new ones
		# Yes, we do this horribly inefficiently, but it doesn't run very
		# often at all...
		re_slot = re.compile('^slot(\d+)$')
		for sess in conference.conferencesession_set.all():
			found = False
			for k,v in request.POST.items():
				if v == "sess%s" % sess.id:
					sm = re_slot.match(k)
					if not sm:
						raise Exception("Could not find slot, invalid data in POST")
					roomid = int(int(sm.group(1)) / 1000000)
					slotid = int(sm.group(1)) % 1000000
					if sess.tentativeroom == None or sess.tentativeroom.id != roomid or sess.tentativescheduleslot == None or sess.tentativescheduleslot.id != slotid:
						sess.tentativeroom = Room.objects.get(pk=roomid)
						sess.tentativescheduleslot = ConferenceSessionScheduleSlot.objects.get(pk=slotid)
						sess.save()
					found=True
					break
			if not found:
				if sess.tentativescheduleslot:
					sess.tentativescheduleslot = None
					sess.save()
		return HttpResponse("OK")

	# Not post - so generate the page

	allrooms = exec_to_keyed_dict("SELECT id, sortkey, roomname FROM confreg_room r WHERE conference_id=%(confid)s ORDER BY sortkey, roomname", {
		'confid': conference.id,
	})
	if len(allrooms) == 0:
		return HttpResponse('No rooms defined for this conference, cannot create schedule yet.')

	# Complete list of all available sessions
	sessions = exec_to_dict("SELECT s.id, track_id, (status = 3) AS ispending, (row_number() over() +1)*75 AS top, title, string_agg(spk.fullname, ', ') AS speaker_list FROM confreg_conferencesession s LEFT JOIN confreg_conferencesession_speaker csp ON csp.conferencesession_id=s.id LEFT JOIN confreg_speaker spk ON spk.id=csp.speaker_id WHERE conference_id=%(confid)s AND status IN (1,3) AND NOT cross_schedule GROUP BY s.id ORDER BY starttime, id", {
		'confid': conference.id,
	})

	# Generate a sessionset with the slots only, but with one slot for
	# each room when we have multiple rooms.
	raw = exec_to_grouped_dict("SELECT s.starttime::date AS day, r.id * 1000000 + s.id AS id, s.starttime, s.endtime, r.id AS room_id, to_char(starttime, 'HH24:MI') || ' - ' || to_char(endtime, 'HH24:MI') AS timeslot, min(starttime) OVER days AS firsttime,max(endtime) OVER days AS lasttime, 'f'::boolean as cross_schedule FROM confreg_conferencesessionscheduleslot s CROSS JOIN confreg_room r WHERE r.conference_id=%(confid)s AND s.conference_id=%(confid)s WINDOW days AS (PARTITION BY s.starttime::date) ORDER BY day, s.starttime", {
		'confid': conference.id,
	})

	if len(raw) == 0:
		return HttpResponse('No schedule slots defined for this conference, cannot create schedule yet.')

	tracks = Track.objects.filter(conference=conference).order_by('sortkey')

	days = []

	for d,d_sessions in raw.items():
		sessionset = SessionSet(allrooms, allrooms, conference.schedulewidth, conference.pixelsperminute, d_sessions)
		days.append({
				'day': d,
				'sessions': sessionset.all(),
				'rooms': sessionset.allrooms(),
				'schedule_height': sessionset.schedule_height(),
				'schedule_width': sessionset.schedule_width(),
				})
	return render(request, 'confreg/schedule_create.html', {
			'conference': conference,
			'days': days,
			'sessions': sessions,
			'tracks': tracks,
			'sesswidth': min(600 / len(allrooms), 150),
			'availableheight': len(sessions)*75,
			'helplink': 'schedule',
			})

@login_required
def publishschedule(request, confname):
	conference = get_authenticated_conference(request, confname)

	transaction.set_autocommit(False)

	changes = []
	# Render a list of changes and a confirm button
	for s in conference.conferencesession_set.all():
		dirty = False
		if s.tentativescheduleslot:
			# It has one, see if it has changed
			if s.starttime:
				# Has an existing time, did it change?
				if s.starttime != s.tentativescheduleslot.starttime or s.endtime != s.tentativescheduleslot.endtime:
					changes.append("Session '%s': moved from '%s' to '%s'" % (s.title, s.starttime, s.tentativescheduleslot.starttime))
					s.starttime = s.tentativescheduleslot.starttime
					s.endtime = s.tentativescheduleslot.endtime
					dirty = True
			else:
				# Previously had no time
				if s.tentativescheduleslot:
					changes.append("Session '%s': now scheduled at '%s'" % (s.title, s.tentativescheduleslot))
					s.starttime = s.tentativescheduleslot.starttime
					s.endtime = s.tentativescheduleslot.endtime
					dirty = True
			if s.room != s.tentativeroom:
				changes.append("Session '%s': changed room from '%s' to '%s'" % (s.title, s.room, s.tentativeroom))
				s.room = s.tentativeroom
				dirty = True
		else:
			if s.starttime:
				changes.append("Session '%s': NOT removed from schedule, do that manually!" % s.title)

		if dirty:
			s.save()

	if request.GET.has_key('doit') and request.GET['doit'] == '1':
		transaction.commit()
		return render(request, 'confreg/schedule_publish.html', {
				'done': 1,
			})
	else:
		transaction.rollback()
		return render(request, 'confreg/schedule_publish.html', {
				'changes': changes,
			})

def reports(request, confname):
	conference = get_authenticated_conference(request, confname)

	# Include information for the advanced reports
	from reports import attendee_report_fields, attendee_report_filters
	return render(request, 'confreg/reports.html', {
			'conference': conference,
			'list': True,
			'additionaloptions': conference.conferenceadditionaloption_set.all(),
			'adv_fields': attendee_report_fields,
			'adv_filters': attendee_report_filters(conference),
			'helplink': 'reports#attendee',
		    })


def advanced_report(request, confname):
	conference = get_authenticated_conference(request, confname)

	if request.method != "POST":
		raise Http404()

	from reports import build_attendee_report

	return build_attendee_report(conference, request.POST )


def simple_report(request, confname):
	conference = get_authenticated_conference(request, confname)

	from reports import simple_reports

	if "__" in request.GET['report']:
		raise Http404("Invalid character in report name")

	if not simple_reports.has_key(request.GET['report']):
		raise Http404("Report not found")

	if conference.personal_data_purged and simple_reports.has_key('{0}__anon'.format(request.GET['report'])):
		query = simple_reports['{0}__anon'.format(request.GET['report'])]
	else:
		query = simple_reports[request.GET['report']]

	curs = connection.cursor()
	curs.execute(query, {
		'confid': conference.id,
		})
	d = curs.fetchall()
	collist = [dd[0] for dd in curs.description]
	# Get offsets of all columns that don't start with _
	colofs = [n for x,n in zip(collist, range(len(collist))) if not x.startswith('_')]
	if len(colofs) != len(collist):
		# One or more columns filtered - so filter the data
		d = map(itemgetter(*colofs), d)

	return render(request, 'confreg/simple_report.html', {
		'conference': conference,
		'columns': [dd for dd in collist if not dd.startswith('_')],
		'data': d,
		'helplink': 'reports',
	})

@login_required
def admin_dashboard(request):
	if request.user.is_superuser:
		conferences = Conference.objects.filter(startdate__gt=datetime.now()-timedelta(days=3*365)).order_by('-startdate')
	else:
		conferences = Conference.objects.filter(administrators=request.user, startdate__gt=datetime.now()-timedelta(days=3*365)).order_by('-startdate')

	# Split conferences in three buckets:
	#  Current: anything that starts or finishes within two weeks
	#  Upcoming: anything newer than that
	#  Past: anything older than that

	current = []
	upcoming = []
	past = []
	for c in conferences:
		if abs((date.today() - c.startdate).days) < 14 or abs((date.today() - c.enddate).days)  < 14:
			current.insert(0, c)
		elif c.startdate > date.today():
			upcoming.insert(0, c)
		else:
			past.append(c)

	return render(request, 'confreg/admin_dashboard.html', {
		'current': current,
		'upcoming': upcoming,
		'past': past,
	})

def admin_dashboard_single(request, urlname):
	conference = get_authenticated_conference(request, urlname)

	return render(request, 'confreg/admin_dashboard_single.html', {
		'conference': conference,
		'pending_session_notifications': conference.pending_session_notifications,
		'pending_waitlist': RegistrationWaitlistEntry.objects.filter(registration__conference=conference, offeredon__isnull=True).exists(),
		'unregistered_staff': exec_to_scalar("SELECT EXISTS (SELECT user_id FROM confreg_conference_staff s WHERE s.conference_id=%(confid)s AND NOT EXISTS (SELECT 1 FROM confreg_conferenceregistration r WHERE r.conference_id=%(confid)s AND payconfirmedat IS NOT NULL AND attendee_id=s.user_id))", {'confid': conference.id}),
		'unregistered_speakers': exec_to_scalar("SELECT EXISTS (SELECT 1 FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker css ON spk.id=css.speaker_id INNER JOIN confreg_conferencesession s ON css.conferencesession_id=s.id WHERE s.conference_id=%(confid)s AND s.status=1 AND NOT EXISTS (SELECT 1 FROM confreg_conferenceregistration r WHERE r.conference_id=%(confid)s AND r.payconfirmedat IS NOT NULL AND r.attendee_id=spk.user_id))", { 'confid': conference.id}),
		'unconfirmed_speakers': exec_to_scalar("SELECT EXISTS (SELECT 1 FROM confreg_conferencesession_speaker css INNER JOIN confreg_conferencesession s ON css.conferencesession_id=s.id WHERE s.conference_id=%(confid)s AND s.status=3)", {'confid': conference.id}),
		'sessions_noroom': exec_to_scalar("SELECT EXISTS (SELECT 1 FROM confreg_conferencesession s WHERE s.conference_id=%(confid)s AND s.status=1 AND s.room_id IS NULL AND NOT cross_schedule)", {'confid': conference.id}),
		'sessions_notrack': exec_to_scalar("SELECT EXISTS (SELECT 1 FROM confreg_conferencesession s WHERE s.conference_id=%(confid)s AND s.status=1 AND s.track_id IS NULL)", {'confid': conference.id}),
		'pending_sessions': conditional_exec_to_scalar(conference.scheduleactive, "SELECT EXISTS (SELECT 1 FROM confreg_conferencesession s WHERE s.conference_id=%(confid)s AND s.status=0)", {'confid': conference.id}),
	})

def admin_registration_dashboard(request, urlname):
	conference = get_authenticated_conference(request, urlname)

	curs = connection.cursor()

	tables = []

	# Registrations by reg type
	curs.execute("""SELECT regtype,
 count(payconfirmedat) AS confirmed,
 count(r.id) FILTER (WHERE payconfirmedat IS NULL AND (r.invoice_id IS NOT NULL OR bp.invoice_id IS NOT NULL)) AS invoiced,
 count(r.id) FILTER (WHERE payconfirmedat IS NULL AND (r.invoice_id IS NULL AND bp.invoice_id IS NULL)) AS unconfirmed,
 count(r.id) AS total
FROM confreg_conferenceregistration r
RIGHT JOIN confreg_registrationtype rt ON rt.id=r.regtype_id
LEFT JOIN confreg_bulkpayment bp ON bp.id=r.bulkpayment_id
WHERE rt.conference_id={0}
GROUP BY rt.id ORDER BY rt.sortkey""".format(conference.id))
	tables.append({'title': 'Registration types',
				   'columns': ['Type', 'Confirmed', 'Invoiced', 'Unconfirmed', 'Total'],
				   'fixedcols': 1,
				   'hidecols': 0,
				   'rows': curs.fetchall()},)

	# Copy/paste string to get the reg status
	statusstr = """{0},
 count(payconfirmedat) AS confirmed,
 count(r.id) FILTER (WHERE payconfirmedat IS NULL AND (r.invoice_id IS NOT NULL)) AS invoiced,
 count(r.id) FILTER (WHERE payconfirmedat IS NULL AND (r.invoice_id IS NULL)) AS unconfirmed,
 count(r.id) AS total,
 CASE WHEN {0} > 0 THEN {0}-count(r.id) ELSE NULL END AS remaining"""

	# Additional options
	curs.execute("""SELECT ao.id, ao.name, {0}
FROM confreg_conferenceregistration r
INNER JOIN confreg_conferenceregistration_additionaloptions rao ON rao.conferenceregistration_id=r.id
RIGHT JOIN confreg_conferenceadditionaloption ao ON ao.id=rao.conferenceadditionaloption_id
LEFT JOIN confreg_bulkpayment bp ON bp.id=r.bulkpayment_id
WHERE ao.conference_id={1} GROUP BY ao.id ORDER BY ao.name""".format(statusstr.format('ao.maxcount'), conference.id))
	tables.append({'title': 'Additional options',
				   'columns': ['id', 'Name', 'Max uses', 'Confirmed', 'Invoiced', 'Unconfirmed', 'Total', 'Remaining'],
				   'fixedcols': 2,
				   'hidecols': 1,
				   'linker': lambda x: '../addopts/{0}/'.format(x[0]),
				   'rows': curs.fetchall()})

	# Discount codes
	curs.execute("""SELECT dc.id, code, validuntil, {0}
FROM confreg_conferenceregistration r
RIGHT JOIN confreg_discountcode dc ON dc.code=r.vouchercode
LEFT JOIN confreg_bulkpayment bp ON bp.id=r.bulkpayment_id
WHERE dc.conference_id={1} AND (r.conference_id={1} OR r.conference_id IS NULL) GROUP BY dc.id ORDER BY code""".format(statusstr.format('maxuses'), conference.id))
	tables.append({'title': 'Discount codes',
				   'columns': ['id', 'Code', 'Expires', 'Max uses', 'Confirmed', 'Invoiced', 'Unconfirmed','Total', 'Remaining'],
				   'fixedcols': 3,
				   'hidecols': 1,
				   'linker': lambda x: '../discountcodes/{0}/'.format(x[0]),
				   'rows': curs.fetchall()})

	# Voucher batches
	curs.execute("SELECT b.id, b.buyername, s.name as sponsorname, count(v.user_id) AS used, count(*) FILTER (WHERE v.user_id IS NULL) AS unused, count(*) AS total FROM confreg_prepaidbatch b INNER JOIN confreg_prepaidvoucher v ON v.batch_id=b.id LEFT JOIN confreg_conferenceregistration r ON r.id=v.user_id LEFT JOIN confsponsor_sponsor s ON s.id = b.sponsor_id WHERE b.conference_id={0} GROUP BY b.id, s.name ORDER BY buyername".format(conference.id))
	tables.append({'title': 'Prepaid vouchers',
				   'columns': ['id', 'Buyer', 'Sponsor', 'Used', 'Unused', 'Total'],
				   'fixedcols': 3,
				   'hidecols': 1,
				   'linker': lambda x: '../prepaid/{0}/'.format(x[0]),
				   'rows': curs.fetchall()})

	# Add a sum row for eveything
	for t in tables:
		sums = ['Total']
		for cn in range(1, t['fixedcols']):
			sums.append('')
		for cn in range(t['fixedcols']-1, len(t['columns'])-1):
			sums.append(sum((r[cn+1] for r in t['rows'] if r[cn+1] != None)))
		t['rows'] = [(r, t.get('linker', lambda x: None)(r)) for r in t['rows']]
		t['rows'].append((sums, None))
	return render(request, 'confreg/admin_registration_dashboard.html', {
		'conference': conference,
		'tables': tables,
		'helplink': 'registrations',
	})

def admin_registration_list(request, urlname):
	conference = get_authenticated_conference(request, urlname)

	skey = request.GET.get('sort', '-date')
	if skey[0] == '-':
		revsort = True
		skey=skey[1:]
	else:
		revsort = False

	sortmap = {
		'last':'lastname',
		'first': 'firstname',
		'company': 'company',
		'type': 'regtype__sortkey',
		'date': 'payconfirmedat',
	}
	if not skey in sortmap:
		return HttpResponse("Bad sort key.")

	return render(request, 'confreg/admin_registration_list.html', {
		'conference': conference,
		'waitlist_active': conference.waitlist_active,
		'sortkey': (revsort and '-' or '') + skey,
		'regs': ConferenceRegistration.objects.select_related('regtype').select_related('registrationwaitlistentry').filter(conference=conference).order_by((revsort and '-' or '') + sortmap[skey], '-created'),
		'regsummary': exec_to_dict("SELECT count(1) FILTER (WHERE payconfirmedat IS NOT NULL) AS confirmed, count(1) FILTER (WHERE payconfirmedat IS NULL) AS unconfirmed FROM confreg_conferenceregistration WHERE conference_id=%(confid)s", {'confid': conference.id})[0],
		'breadcrumbs': (('/events/admin/{0}/regdashboard/'.format(urlname), 'Registration dashboard'),),
		'helplink': 'registrations',
	})

def admin_registration_single(request, urlname, regid):
	conference = get_authenticated_conference(request, urlname)

	reg = get_object_or_404(ConferenceRegistration, id=regid, conference=conference)

	if reg.attendee:
		sessions = ConferenceSession.objects.filter(conference=conference, speaker__user=reg.attendee)
	else:
		sessions = None
	return render(request, 'confreg/admin_registration_single.html', {
		'conference': conference,
		'reg': reg,
		'sessions': sessions,
		'signups': _get_registration_signups(conference, reg),
		'breadcrumbs': (
			('/events/admin/{0}/regdashboard/'.format(urlname), 'Registration dashboard'),
			('/events/admin/{0}/regdashboard/list/'.format(urlname), 'Registration list'),
		),
		'helplink': 'registrations',
	})

@transaction.atomic
def admin_registration_cancel(request, urlname, regid):
	conference = get_authenticated_conference(request, urlname)

	reg = get_object_or_404(ConferenceRegistration, id=regid, conference=conference)

	if request.method == 'POST' and request.POST.get('docancel') == '1':
		name = reg.fullname
		cancel_registration(reg)
		return render(request, 'confreg/admin_registration_cancel_confirm.html', {
			'conference': conference,
			'name': name,
		})
	else:
		return render(request, 'confreg/admin_registration_cancel.html', {
			'conference': conference,
			'reg': reg,
			'helplink': 'waitlist',
		})

@transaction.atomic
def admin_registration_clearcode(request, urlname, regid):
	conference = get_authenticated_conference(request, urlname)

	reg = get_object_or_404(ConferenceRegistration, id=regid, conference=conference)
	if reg.has_invoice():
		messages.warning(request, "Cannot clear the code from a registration with an invoice")
	else:
		messages.info(request, "Removed voucher code '{0}'".format(reg.vouchercode))
		reg.vouchercode = ""
		reg.save()
	return HttpResponseRedirect("../")

@transaction.atomic
def admin_waitlist(request, urlname):
	conference = get_authenticated_conference(request, urlname)

	if conference.attendees_before_waitlist <= 0:
		return render(request, 'confreg/admin_waitlist_inactive.html', {
			'conference': conference,
			'helplink': 'waitlist',
			})

	num_confirmedregs = ConferenceRegistration.objects.filter(conference=conference, payconfirmedat__isnull=False).count()
	num_invoicedregs = ConferenceRegistration.objects.filter(conference=conference, payconfirmedat__isnull=True, invoice__isnull=False, registrationwaitlistentry__isnull=True).count()
	num_invoicedbulkpayregs = ConferenceRegistration.objects.filter(conference=conference, payconfirmedat__isnull=True, bulkpayment__isnull=False, bulkpayment__paidat__isnull=True).count()
	num_waitlist_offered = RegistrationWaitlistEntry.objects.filter(registration__conference=conference, offeredon__isnull=False, registration__payconfirmedat__isnull=True).count()
	waitlist = RegistrationWaitlistEntry.objects.filter(registration__conference=conference, registration__payconfirmedat__isnull=True).order_by('enteredon')
	waitlist_cleared = RegistrationWaitlistEntry.objects.filter(registration__conference=conference, registration__payconfirmedat__isnull=False).order_by('-registration__payconfirmedat', 'enteredon')

	if request.method == 'POST':
		# Attempting to make an offer
		form = WaitlistOfferForm(data=request.POST)
		if form.is_valid():
			regs = ConferenceRegistration.objects.filter(conference=conference, id__in=form.reg_list)
			if len(regs) != len(form.reg_list):
				raise Exception("Database lookup mismatch")
			if len(regs) < 1:
				raise Exception("Somehow got through with zero!")

			for r in regs:
				wl = r.registrationwaitlistentry
				if wl.offeredon:
					raise Exception("One or more already offered!")
				wl.offeredon = datetime.now()
				if request.POST.get('submit') == 'Make offer for hours':
					wl.offerexpires = datetime.now() + timedelta(hours=form.cleaned_data['hours'])
					RegistrationWaitlistHistory(waitlist=wl,
												text="Made offer valid for {0} hours by {1}".format(form.cleaned_data['hours'], request.user.username)).save()
				else:
					wl.offerexpires = form.cleaned_data['until']
					RegistrationWaitlistHistory(waitlist=wl,
												text="Made offer valid until {0} by {1}".format(form.cleaned_data['until'], request.user.username)).save()
				wl.save()
				send_template_mail(conference.contactaddr,
								   r.email,
								   "Your waitlisted registration for {0}".format(conference.conferencename),
								   'confreg/mail/waitlist_offer.txt',
								   {
									   'conference': conference,
									   'reg': r,
									   'offerexpires': wl.offerexpires,
								   },
								   sendername = conference.conferencename,
								   receivername = r.fullname,
							   )
				messages.info(request, "Sent offer to {0}".format(r.email))
			return HttpResponseRedirect(".")
	else:
		form = WaitlistOfferForm()

	return render(request, 'confreg/admin_waitlist.html', {
		'conference': conference,
		'num_confirmedregs': num_confirmedregs,
		'num_invoicedregs': num_invoicedregs,
		'num_invoicedbulkpayregs': num_invoicedbulkpayregs,
		'num_waitlist_offered': num_waitlist_offered,
		'num_total': num_confirmedregs + num_invoicedregs + num_invoicedbulkpayregs + num_waitlist_offered,
		'waitlist': waitlist,
		'waitlist_cleared': waitlist_cleared,
		'form': form,
		'helplink': 'waitlist',
		})

@transaction.atomic
def admin_waitlist_cancel(request, urlname, wlid):
	conference = get_authenticated_conference(request, urlname)

	wl = get_object_or_404(RegistrationWaitlistEntry, pk=wlid, registration__conference=conference)
	reg = wl.registration
	if wl.offeredon:
		# Active offer means we are moving this entry back onto the waitlist
		RegistrationWaitlistHistory(waitlist=wl,
									text="Offer canceled by {0}".format(request.user.username)).save()
		wl.offeredon = None
		wl.offerexpires = None
		wl.enteredon = datetime.now()
		wl.save()

		send_simple_mail(reg.conference.contactaddr,
						 reg.conference.contactaddr,
						 'Waitlist offer cancel',
						 u'Waitlist offer for user {0} {1} <{2}> canceled by {3}. User remains on waitlist.'.format(reg.firstname, reg.lastname, reg.email, request.user),
						 sendername=reg.conference.conferencename)

		send_template_mail(reg.conference.contactaddr,
						   reg.email,
						   'Waitlist offer canceled',
						   'confreg/mail/waitlist_admin_offer_cancel.txt',
						   {
							   'conference': conference,
							   'reg': reg,
						   },
						   sendername=reg.conference.conferencename,
						   receivername=reg.fullname,
		)
		messages.info(request, "Waitlist offer canceled.")

	else:
		# No active offer means we are canceling the entry completely
		wl.delete()

		send_simple_mail(reg.conference.contactaddr,
						 reg.conference.contactaddr,
						 'Waitlist cancel',
						 u'User {0} {1} <{2}> removed from the waitlist by {3}.'.format(reg.firstname, reg.lastname, reg.email, request.user),
						 sendername=reg.conference.conferencename)

		send_template_mail(reg.conference.contactaddr,
						   reg.email,
						   'Waitlist canceled',
						   'confreg/mail/waitlist_admin_cancel.txt',
						   {
							   'conference': conference,
							   'reg': reg,
						   },
						   sendername=reg.conference.conferencename,
						   receivername=reg.fullname,
		)

		messages.info(request, "Waitlist entry removed.")
	return HttpResponseRedirect("../../")


@transaction.atomic
def admin_attendeemail(request, urlname):
	conference = get_authenticated_conference(request, urlname)

	mails = AttendeeMail.objects.filter(conference=conference)

	if request.method == 'POST':
		form = AttendeeMailForm(conference, data=request.POST)
		if form.is_valid():
			msg = AttendeeMail(conference=conference,
							   subject=form.data['subject'],
							   message=form.data['message'])
			msg.save()
			for rc in form.data.getlist('regclasses'):
				msg.regclasses.add(rc)
			msg.save()

			# Now also send the email out to the currently registered attendees
			attendees = ConferenceRegistration.objects.filter(conference=conference, payconfirmedat__isnull=False, regtype__regclass__in=form.data.getlist('regclasses'))
			for a in attendees:
				msgtxt = u"{0}\n\n-- \nThis message was sent to attendees of {1}.\nYou can view all communications for this conference at:\n{2}/events/{3}/register/\n".format(msg.message, conference, settings.SITEBASE, conference.urlname)
				send_simple_mail(conference.contactaddr,
								 a.email,
								 u"[{0}] {1}".format(conference, msg.subject),
								 msgtxt,
								 sendername=conference.conferencename,
								 receivername=a.fullname,
								 )
			messages.info(request, "Email sent to %s attendees, and added to registration pages" % len(attendees))
			return HttpResponseRedirect(".")
	else:
		form = AttendeeMailForm(conference)

	return render(request, 'confreg/admin_mail.html', {
		'conference': conference,
		'mails': mails,
		'form': form,
		'helplink': 'emails',
	})

def admin_attendeemail_view(request, urlname, mailid):
	conference = get_authenticated_conference(request, urlname)

	mail = get_object_or_404(AttendeeMail, conference=conference, pk=mailid)

	return render(request, 'confreg/admin_mail_view.html', {
		'conference': conference,
		'mail': mail,
		'breadcrumbs': (('/events/admin/{0}/mail/'.format(conference.urlname), 'Attendee emails'), ),
		'helplink': 'emails',
		})

@transaction.atomic
def session_notify_queue(request, urlname):
	conference = get_authenticated_conference(request, urlname)

	notifysessions = ConferenceSession.objects.filter(conference=conference).exclude(status=F('lastnotifiedstatus'))

	if request.method == 'POST' and request.POST.has_key('confirm_sending') and request.POST['confirm_sending'] == '1':
		# Ok, it would appear we should actually send them...
		num = 0
		for s in notifysessions:
			for spk in s.speaker.all():
				send_template_mail(conference.contactaddr,
								   spk.user.email,
								   "Your session '%s' submitted to %s" % (s.title, conference),
								   'confreg/mail/session_notify.txt',
								   {
									   'conference': conference,
									   'session': s,
								   },
								   sendername=conference.conferencename,
								   receivername=spk.fullname,
							   )
				num += 1
			s.lastnotifiedstatus = s.status
			s.lastnotifiedtime = datetime.now()
			s.save()
		messages.info(request, 'Sent email to %s recipients, for %s sessions' % (num, len(notifysessions)))
		return HttpResponseRedirect('.')

	return render(request, 'confreg/admin_session_queue.html', {
		'conference': conference,
		'notifysessions': notifysessions,
		})

@transaction.atomic
def transfer_reg(request, urlname):
	conference = get_authenticated_conference(request, urlname)

	def _make_transfer(fromreg, toreg):
		yield u"Initiating transfer from %s to %s" % (fromreg.fullname, toreg.fullname)
		if toreg.payconfirmedat:
			raise ValidationError("Destination registration is already confirmed!")
		if toreg.bulkpayment:
			raise ValidationError("Destination registration is part of a bulk payment")
		if toreg.invoice:
			raise ValidationError("Destination registration has an invoice")

		if toreg.additionaloptions.exists():
			raise ValidationError("Destination registration has additional options")

		if hasattr(toreg, 'registrationwaitlistentry'):
			raise ValidationError("Destination registration is on the waitlist")

		# Transfer registration type
		if toreg.regtype != fromreg.regtype:
			yield u"Change registration type from %s to %s" % (toreg.regtype, fromreg.regtype)
			if fromreg.regtype.specialtype:
				try:
					validate_special_reg_type(fromreg.regtype.specialtype, toreg)
				except ValidationError, e:
					raise ValidationError("Registration type cannot be transferred: %s" % e.message)
			toreg.regtype = fromreg.regtype

		# Transfer any vouchers
		if fromreg.vouchercode != toreg.vouchercode:
			yield u"Change discount code to %s" % fromreg.vouchercode
			if toreg.vouchercode:
				# There's already a code set. Remove it.
				toreg.vouchercode = None

				# Actively attached to a discount code. Can't deal with that
				# right now.
				if toreg.discountcode_set.exists():
					raise ValidationError("Receiving registration is connected to discount code. Cannot handle.")
			if fromreg.vouchercode:
				# It actually has one. So we have to transfer it
				toreg.vouchercode = fromreg.vouchercode
				dcs = fromreg.discountcode_set.all()
				if dcs:
					# It's a discount code. There can only ever be one.
					d = dcs[0]
					d.registrations.remove(fromreg)
					d.registrations.add(toreg)
					d.save()
					yield u"Transferred discount code %s" % d
				vcs = fromreg.prepaidvoucher_set.all()
				if vcs:
					# It's a voucher code. Same here, only one.
					v = vcs[0]
					v.user = toreg
					v.save()

		# Bulk payment?
		if fromreg.bulkpayment:
			yield u"Transfer bulk payment %s" % fromreg.bulkpayment.id
			toreg.bulkpayment = fromreg.bulkpayment
			fromreg.bulkpayment = None

		# Invoice?
		if fromreg.invoice:
			yield u"Transferring invoice %s" % fromreg.invoice.id
			toreg.invoice = fromreg.invoice
			fromreg.invoice = None
			InvoiceHistory(invoice=toreg.invoice,
						   txt="Transferred from {0} to {1}".format(fromreg.email, toreg.email)
						   ).save()


		# Additional options
		if fromreg.additionaloptions.exists():
			for o in fromreg.additionaloptions.all():
				yield u"Transferring additional option {0}".format(o)
				o.conferenceregistration_set.remove(fromreg)
				o.conferenceregistration_set.add(toreg)
				o.save()

		# Waitlist entries
		if hasattr(fromreg, 'registrationwaitlistentry'):
			wle = fromreg.registrationwaitlistentry
			yield u"Transferring registration waitlist entry"
			wle.registration = toreg
			wle.save()

		yield u"Copying payment confirmation"
		toreg.payconfirmedat = fromreg.payconfirmedat
		toreg.payconfirmedby = "{0}(x)".format(fromreg.payconfirmedby)[:16]
		toreg.save()

		yield "Sending notification to target registration"
		notify_reg_confirmed(toreg, False)

		yield "Sending notification to source registration"
		send_template_mail(fromreg.conference.contactaddr,
						   fromreg.email,
						   "[{0}] Registration transferred".format(fromreg.conference),
						   'confreg/mail/reg_transferred.txt', {
							   'conference': conference,
							   'toreg': toreg,
						   },
						   sendername=fromreg.conference.conferencename,
						   receivername=fromreg.fullname)

		send_simple_mail(fromreg.conference.contactaddr,
						   fromreg.conference.contactaddr,
						   "Transferred registration",
						   "Registration for {0} transferred to {1}.\n".format(fromreg.email, toreg.email),
						   sendername=fromreg.conference.conferencename,
						   receivername=fromreg.conference.conferencename,
						   )

		yield u"Deleting old registration"
		fromreg.delete()

	steps = None
	stephash = None
	if request.method == 'POST':
		form = TransferRegForm(conference, data=request.POST)
		if form.is_valid():
			savepoint = transaction.savepoint()
			try:
				steps = list(_make_transfer(form.cleaned_data['transfer_from'],
											form.cleaned_data['transfer_to'],
											))
			except ValidationError, e:
				form.add_error(None, e)
				form.remove_confirm()

			if steps:
				sh = SHA256.new()
				for s in steps:
					sh.update(s.encode('utf8'))
				stephash = sh.hexdigest()

			if form.cleaned_data['confirm']:
				if stephash != request.POST.get('stephash', None):
					messages.error(request, 'Something changed while running. Start over!')
					transaction.set_rollback(True)
					return HttpResponseRedirect('.')
				transaction.savepoint_commit(savepoint)
				messages.info(request,"Registration transfer completed.")
				return HttpResponseRedirect('../')
			else:
				transaction.savepoint_rollback(savepoint)

			# Fall through!
	else:
		form = TransferRegForm(conference)

	return render(request, 'confreg/admin_transfer.html', {
		'conference': conference,
		'form': form,
		'steps': steps,
		'stephash': stephash,
		'helplink': 'registrations#transfer',
	})


# Send email to attendees of mixed conferences
@superuser_required
@transaction.atomic
def crossmail(request):
	def _get_recipients_for_crossmail(postdict):
		def _get_one_filter(conf, filt, optout_filter=False):
			(t,v) = filt.split(':')
			if t == 'rt':
				# Regtype
				q = "SELECT attendee_id, email, firstname || ' ' || lastname, regtoken FROM confreg_conferenceregistration WHERE conference_id={0} AND payconfirmedat IS NOT NULL".format(int(conf))
				if v != '*':
					q += ' AND regtype_id={0}'.format(int(v))
				if optout_filter:
					q += " AND NOT EXISTS (SELECT 1 FROM confreg_conferenceseriesoptout INNER JOIN confreg_conference ON confreg_conference.series_id=confreg_conferenceseriesoptout.series_id WHERE user_id=attendee_id AND confreg_conference.id={0})".format(int(conf))
			elif t == 'sp':
				# Speaker
				if v == '*':
					sf=""
				elif v == '?':
					sf = " AND status IN (1,3)"
				else:
					sf = " AND status = {0}".format(int(v))

				q = "SELECT user_id, email, fullname, speakertoken FROM confreg_speaker INNER JOIN auth_user ON auth_user.id=confreg_speaker.user_id WHERE EXISTS (SELECT 1 FROM confreg_conferencesession_speaker INNER JOIN confreg_conferencesession ON confreg_conferencesession.id=conferencesession_id WHERE speaker_id=confreg_speaker.id AND conference_id={0}{1})".format(int(conf), sf)
				if optout_filter:
					q += " AND NOT EXISTS (SELECT 1 FROM confreg_conferenceseriesoptout INNER JOIN confreg_conference ON confreg_conference.series_id=confreg_conferenceseriesoptout.series_id WHERE confreg_conferenceseriesoptout.user_id=confreg_speaker.user_id AND confreg_conference.id={0})".format(int(conf))
			else:
				raise Exception("Invalid filter type")
			return q

		if postdict['include'] == '':
			return []

		# Parse all includes and excludes
		incs = [_get_one_filter(*i.split('@'), optout_filter=True) for i in postdict['include'].split(';') if i != '']
		excs = [_get_one_filter(*i.split('@')) for i in postdict['exclude'].split(';') if i != '']

		q = StringIO()
		q.write("WITH incs (userid, email, fullname, token) AS (")
		q.write("\nUNION ALL\n".join(incs))
		q.write("\n)")
		if excs:
			q.write(", excs (userid, email, fullname, token) AS (\n")
			q.write("\nUNION ALL\n".join(excs))
			q.write("\n)\n")
		q.write("SELECT DISTINCT ON (email) email, fullname, token FROM incs\n")
		q.write(" WHERE (userid IS NULL OR userid NOT IN (SELECT user_id FROM confreg_globaloptout))\n")
		if excs:
			q.write(" and email NOT IN (SELECT email FROM excs)\n")
		q.write("ORDER BY email")

		return exec_to_dict(q.getvalue())

	if request.method == 'POST':
		form = CrossConferenceMailForm(data=request.POST)

		recipients = _get_recipients_for_crossmail(request.POST)

		if form.is_valid() and recipients:
			for r in recipients:
				send_simple_mail(form.data['senderaddr'],
								 r['email'],
								 form.data['subject'],
								 u"{0}\n\n\nThis email was sent to you from {1}.\nTo opt-out from further communications about our events, please fill out the form at:\n{2}/events/optout/{3}/".format(form.data['text'], settings.ORG_NAME, settings.SITEBASE, r['token']),
								 sendername=form.data['sendername'],
								 receivername=r['fullname'],
				)

			messages.info(request, "Sent {0} emails.".format(len(recipients)))
			return HttpResponseRedirect("../")
		if not recipients:
			form.add_error(None, "No recipients matched")
			form.remove_confirm()
	else:
		form = CrossConferenceMailForm()
		recipients = None

	return render(request, 'confreg/admin_cross_conference_mail.html', {
		'form': form,
		'recipients': recipients,
		'conferences': Conference.objects.all(),
		'helplink': 'emails#crossconference',
		})


@superuser_required
@transaction.atomic
def crossmailoptions(request):
	conf = get_object_or_404(Conference, id=request.GET['conf'])

	# Get a list of different crossmail options for this conference. Note that
	# each of them must have an implementation in _get_one_filter() or bad things
	# will happen.
	r = [
		{'id': 'rt:*', 'title': 'Reg: all'},
	]
	r.extend([
		{'id': 'rt:{0}'.format(rt.id), 'title': 'Reg: {0}'.format(rt.regtype)}
		for rt in RegistrationType.objects.filter(conference=conf)])
	r.extend([
		{'id': 'sp:*', 'title': 'Speaker: all'},
		{'id': 'sp:?', 'title': 'Speaker: accept+reserve'},
	])
	r.extend([
		{'id': 'sp:{0}'.format(k), 'title': 'Speaker: {0}'.format(v)}
		for k,v in STATUS_CHOICES
	])
	return HttpResponse(json.dumps(r), content_type="application/json")

# Admin view that's used to send email to multiple users
@superuser_required
@transaction.atomic
def admin_email(request):
	if request.method == 'POST':
		form = EmailSendForm(data=request.POST)
		if form.is_valid():
			# Ok, actually send the email. This is the scary part!
			ids = form.data['ids'].split(',')
			regs = ConferenceRegistration.objects.filter(pk__in=ids)
			emails = [r.email for r in regs]
			msg = MIMEText(form.data['text'], _charset='utf-8')
			msg['Subject'] = form.data['subject']
			msg['From'] = form.data['sender']
			msg['To'] = form.data['sender']
			for e in emails:
				send_mail(form.data['sender'], e, msg.as_string())

			messages.info(request, 'Sent email to %s recipients' % len(emails))
			return HttpResponseRedirect('/admin/confreg/conferenceregistration/?' + form.data['returnurl'])
		else:
			ids = form.data['ids'].split(',')
	else:
		ids = request.GET['ids']
		form = EmailSendForm(initial={'ids': ids, 'returnurl': request.GET['orig']})
		ids = ids.split(',')

	recipients = [r.email for r in ConferenceRegistration.objects.filter(pk__in=ids)]
	return render(request, 'confreg/admin_email.html', {
		'form': form,
		'recipientlist': ', '.join(recipients),
		})


@superuser_required
@transaction.atomic
def admin_email_session(request, sessionids):
	sessions = ConferenceSession.objects.filter(pk__in=sessionids.split(','))
	speakers = Speaker.objects.filter(conferencesession__in=sessions).distinct()

	if request.method == 'POST':
		form = EmailSessionForm(data=request.POST)
		if form.is_valid():
			# Ok, actually send the email. This is the scary part!
			emails = [speaker.user.email for speaker in speakers]
			for e in emails:
				msg = MIMEText(form.data['text'], _charset='utf-8')
				msg['Subject'] = form.data['subject']
				msg['From'] = form.data['sender']
				msg['To'] = e
				send_mail(form.data['sender'], e, msg.as_string())

			messages.info(request, 'Sent email to %s recipients (%s)' % (len(emails), ", ".join(emails)))
			if ',' in sessionids:
				# We always get the original URL as a query parameter in this
				# case.
				return HttpResponseRedirect('/admin/confreg/conferencesession/?' + form.data['returnurl'])
			else:
				return HttpResponseRedirect('/admin/confreg/conferencesession/%s/' % sessionids)
	else:
		form = EmailSessionForm(initial={'sender': sessions[0].conference.contactaddr, 'returnurl': request.GET.has_key('orig') and request.GET['orig'] or ''})


	return render(request, 'confreg/admin_email.html', {
		'form': form,
		'recipientlist': ", ".join([s.name for s in speakers]),
		'whatfor': ", ".join(['Session "%s"' % s.title for s in sessions]),
		})


# Redirect from old style event URLs
def legacy_redirect(self, what, confname, resturl=None):
	# Fallback to most basic syntax
	if resturl:
		return HttpResponsePermanentRedirect('/events/{0}/{1}/{2}'.format(confname, what, resturl))
	else:
		return HttpResponsePermanentRedirect('/events/{0}/{1}/'.format(confname, what))
