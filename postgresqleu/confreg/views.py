#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.template import RequestContext, Context
from django.template.loader import get_template
from django.template.base import TemplateDoesNotExist
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.db import transaction, connection
from django.db.models import Q, Count
from django.db.models.expressions import F
from django.forms import formsets
from django.forms import ValidationError

from models import Conference, ConferenceRegistration, ConferenceSession
from models import ConferenceSessionSlides, ConferenceSeries
from models import ConferenceSeriesOptOut, GlobalOptOut
from models import ConferenceSessionFeedback, Speaker, Speaker_Photo
from models import ConferenceFeedbackQuestion, ConferenceFeedbackAnswer
from models import RegistrationType, PrepaidVoucher, PrepaidBatch, DiscountCode
from models import BulkPayment, Room, Track, ConferenceSessionScheduleSlot
from models import AttendeeMail, ConferenceAdditionalOption
from models import PendingAdditionalOrder
from models import RegistrationWaitlistEntry, RegistrationWaitlistHistory
from models import STATUS_CHOICES
from forms import ConferenceRegistrationForm, ConferenceSessionFeedbackForm
from forms import ConferenceFeedbackForm, SpeakerProfileForm
from forms import CallForPapersForm, CallForPapersSpeakerForm, CallForPapersSubmissionForm
from forms import PrepaidCreateForm, BulkRegistrationForm
from forms import EmailSendForm, EmailSessionForm, CrossConferenceMailForm
from forms import AttendeeMailForm, WaitlistOfferForm, TransferRegForm
from forms import SessionSlidesUrlForm, SessionSlidesFileForm
from util import invoicerows_for_registration, notify_reg_confirmed
from util import get_invoice_autocancel

from models import get_status_string
from regtypes import confirm_special_reg_type, validate_special_reg_type
from jinjafunc import render_jinja_conference_response

from postgresqleu.util.decorators import user_passes_test_or_error
from postgresqleu.util.random import generate_random_token
from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod, InvoiceRow
from postgresqleu.confwiki.models import Wikipage
from postgresqleu.invoices.util import InvoiceManager, InvoicePresentationWrapper
from postgresqleu.invoices.models import InvoiceProcessor, InvoiceHistory
from postgresqleu.mailqueue.util import send_mail, send_simple_mail, send_template_mail, template_to_string
from postgresqleu.util.jsonutil import JsonSerializer
from postgresqleu.util.db import exec_to_dict, exec_to_grouped_dict, exec_to_keyed_dict
from postgresqleu.util.db import exec_no_result, exec_to_list

from decimal import Decimal
from operator import itemgetter
from datetime import datetime, timedelta, date
import base64
import re
import os
import sys
import imp
from email.mime.text import MIMEText
from Crypto.Hash import SHA256
from StringIO import StringIO

import json

#
# The ConferenceContext allows overriding of the 'conftemplbase' variable,
# which is used to control the base template of all the confreg web pages.
# This allows a single conference to override the "framework" template
# around itself, while retaining all the contents.
#
def ConferenceContext(request, conference):
	d = RequestContext(request)
	if conference and conference.template_override:
		conftemplbase = conference.template_override
	else:
		conftemplbase = "nav_events.html"
	d.update({
			'conftemplbase': conftemplbase,
			'conference': conference,
			})
	if conference and conference.mediabase_override:
		d['mediabase'] = conference.mediabase_override

	# Check if there is any additional data to put into the context
	if conference and conference.templatemodule:
		try:
			modname = 'conference_templateextra_%s' % conference.id
			if modname in sys.modules:
				m = sys.modules[modname]
			else:
				# Not loaded, so try to load it!
				m = imp.load_source(modname, '%s/templateextra.py' % conference.templatemodule)
			d.update(m.context_template_additions())
		except Exception:
			# Ignore problems, because we're lazy. Better render without the
			# data than not render at all.
			pass

	return d

#
# Render a conference page. This automatically attaches the ConferenceContext.
# It will also load the template from the override directory if one is configured
# on the conference.
#
def render_conference_response(request, conference, pagemagic, templatename, dictionary=None):
	# Conference can be None for pages that can be both inside and outside
	# the framework, such as the speaker profile.
	if conference and conference.jinjadir:
		# Use the cleaner (?) jinja based rendering system
		return render_jinja_conference_response(request, conference, pagemagic, templatename, dictionary)

	context = ConferenceContext(request, conference)
	context['pagemagic'] = pagemagic
	if conference and conference.templateoverridedir:
		try:
			if request.GET.has_key('test') and request.GET['test'] == '1':
				# If we append the test=1 parameter to the URL, we get a test version of
				# the templates. Basically we just append ".test" to the end of the template
				# name, making it possible to play interesting symlink tricks and such things
				# to do testing in production env.
				templatename += ".test"

			tmpl = get_template(templatename, [conference.templateoverridedir,])

			if dictionary:
				context.update(dictionary)
			return HttpResponse(tmpl.render(context))
		except TemplateDoesNotExist:
			# Template not found, so fall through to the default and load the template
			# from our main directory.
			pass

	# Either no override configured, or override not found
	return render_to_response(templatename, dictionary, context_instance=context)

# Not a view in itself, only called from other views
def _registration_dashboard(request, conference, reg):
	mails = AttendeeMail.objects.filter(conference=conference, regclasses=reg.regtype.regclass)

	wikipagesQ = Q(publicview=True) | Q(viewer_attendee__attendee=request.user) | Q(viewer_regtype__conferenceregistration__attendee=request.user)
	wikipages = Wikipage.objects.filter(Q(conference=conference) & wikipagesQ).distinct()

	# Left join is hard to do efficiently with the django ORM, so let's do a query instead
	cursor = connection.cursor()
	cursor.execute("SELECT s.id, s.title, s.deadline, s.deadline < CURRENT_TIMESTAMP, ats.saved FROM confwiki_signup s LEFT JOIN confwiki_attendeesignup ats ON (s.id=ats.signup_id AND ats.attendee_id=%(regid)s) WHERE s.conference_id=%(confid)s AND (s.deadline IS NULL OR s.deadline > CURRENT_TIMESTAMP OR ats.saved IS NOT NULL) AND (s.public OR EXISTS (SELECT 1 FROM confwiki_signup_attendees sa WHERE sa.signup_id=s.id AND sa.conferenceregistration_id=%(regid)s) OR EXISTS (SELECT 1 FROM confwiki_signup_regtypes sr WHERE sr.signup_id=s.id AND sr.registrationtype_id=%(regtypeid)s)) ORDER  BY 4 DESC, 3, 2", {
		'confid': conference.id,
		'regid': reg.id,
		'regtypeid': reg.regtype_id,
		})
	signups = [dict(zip(['id', 'title', 'deadline', 'closed', 'savedat'], r)) for r in cursor.fetchall()]

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

	return render_conference_response(request, conference, 'reg', 'confreg/registration_dashboard.html', {
		'reg': reg,
		'is_speaker': is_speaker,
		'mails': mails,
		'wikipages': wikipages,
		'signups': signups,
		'availableoptions': availableoptions,
		'pendingadditional': pendingadditional,
		'pendingadditionalinvoice': pendingadditionalinvoice,
		'invoices': invoices,
	})

@login_required
@transaction.atomic
def home(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	try:
		reg = ConferenceRegistration.objects.get(conference=conference,
			attendee=request.user)
	except:
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
			return _registration_dashboard(request, conference, reg)
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

		form = ConferenceRegistrationForm(request.user, data=request.POST, instance=reg)
		if form.is_valid():
			reg = form.save(commit=False)
			reg.conference = conference
			reg.attendee = request.user
			reg.save()
			form.save_m2m()
			form_is_saved = True

			# Figure out if the user clicked a "magic save button"
			if request.POST['submit'] == 'Confirm and finish' or request.POST['submit'] == 'Save and finish':
				# Complete registration!
				return HttpResponseRedirect("confirm/")

			# Or did they click cancel?
			if request.POST['submit'] == 'Cancel registration':
				reg.delete()
				return HttpResponseRedirect("canceled/")

			# Else it was a general save, and we'll fall through and
			# show the form again so details can be edited.
	else:
		# This is just a get. Depending on the state of the registration,
		# we may want to show the form or not.
		if reg.payconfirmedat:
			# This registration is completed. Show the dashboard instead of
			# the registration form.
			return _registration_dashboard(request, conference, reg)

		if reg.invoice or reg.bulkpayment:
			# Invoice generated or part of bulk payment means the registration
			# can't be changed any more (without having someone cancel the
			# invoice).

			return render_conference_response(request, conference, 'reg', 'confreg/regform_completed.html', {
				'reg': reg,
				'invoice': InvoicePresentationWrapper(reg.invoice, "%s/events/register/%s/" % (settings.SITEBASE, conference.urlname)),
			})

		# Else fall through and render the form
		form = ConferenceRegistrationForm(request.user, instance=reg)

	return render_conference_response(request, conference, 'reg', 'confreg/regform.html', {
		'form': form,
		'form_is_saved': form_is_saved,
		'reg': reg,
		'invoice': InvoicePresentationWrapper(reg.invoice, "%s/events/register/%s/" % (settings.SITEBASE, conference.urlname)),
		'additionaloptions': conference.conferenceadditionaloption_set.filter(public=True),
		'costamount': reg.regtype and reg.regtype.cost or 0,
	})

def feedback_available(request):
	conferences = Conference.objects.filter(feedbackopen=True).order_by('startdate')
	return render_to_response('confreg/feedback_available.html', {
		'conferences': conferences,
	}, context_instance=RequestContext(request))

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
		print(day_rooms.keys())
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

@login_required
def schedulejson(request, confname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confname)
	else:
		conference = get_object_or_404(Conference, urlname=confname, administrators=request.user)

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
	return render_to_response('confreg/schedule.ical', {
		'conference': conference,
		'sessions': sessions,
		'servername': request.META['SERVER_NAME'],
	}, content_type='text/calendar', context_instance=RequestContext(request))

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
def speakerprofile(request, confurlname=None):
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
			speaker.generate_random_token()
			speaker.save()

		form = SpeakerProfileForm(data=request.POST, files=request.FILES, instance=speaker)
		if form.is_valid():
			if request.FILES.has_key('photo'):
				raise Exception("Deal with the file!")
			form.save()
			return HttpResponseRedirect('.')
	else:
		form = SpeakerProfileForm(instance=speaker)

	if confurlname:
		conf = get_object_or_404(Conference, urlname=confurlname)
	else:
		conf = None
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
	except Speaker.DoesNotExist:
		sessions = []

	return render_conference_response(request, conference, 'cfp', 'confreg/callforpapers.html', {
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
		speaker, created = Speaker.objects.get_or_create(user=request.user)
		if created:
			speaker.fullname = request.user.first_name
			speaker.save()

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

	savedok = False

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
		return HttpResponseRedirect("/events/register/%s/" % conference.urlname)

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

	if request.method == 'POST':
		if request.POST['submit'].find('Back') >= 0:
			return HttpResponseRedirect("../")
		if request.POST['submit'] == 'Confirm and finish':
			# Get the invoice rows and flag any vouchers as used
			# (committed at the end of the view so if something
			# goes wrong they automatically go back to unused)
			invoicerows = invoicerows_for_registration(reg, True)
			totalcost = sum([r[2]*(1+(r[3] and r[3].vatpercent or 0)/Decimal(100.0)) for r in invoicerows])

			if len(invoicerows) <= 0:
				return HttpResponseRedirect("../")

			if totalcost == 0:
				# Paid in total with vouchers, or completely free
				# registration type. So just flag the registration
				# as confirmed.
				reg.payconfirmedat = datetime.today()
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
	invoicerows = invoicerows_for_registration(reg, False)
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
			'invoice': InvoicePresentationWrapper(reg.invoice, "%s/events/register/%s/" % (settings.SITEBASE, conference.urlname)),
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
def optout(request, token):
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

	return render_to_response('confreg/optout.html', {
		'email': email,
		'globaloptout': GlobalOptOut.objects.filter(user=userid).exists(),
		'series': series,
	},context_instance=RequestContext(request))

@login_required
@transaction.atomic
@user_passes_test_or_error(lambda u: u.has_module_perms('invoicemgr'))
def createvouchers(request):
	# Creation of pre-paid vouchers for conference registrations
	if request.method == 'POST':
		form = PrepaidCreateForm(data=request.POST)
		if form.is_valid():
			# All data is correct, create the vouchers
			# (by first creating a batch)

			conference = Conference.objects.get(pk=form.data['conference'])
			regtype = RegistrationType.objects.get(pk=form.data['regtype'], conference=conference)
			regcount = int(form.data['count'])
			buyer = User.objects.get(pk=form.data['buyer'])
			buyername = form.data['buyername']

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
												  ))
				invoice.allowedmethods = InvoicePaymentMethod.objects.filter(auto=True)
				invoice.save()
			return HttpResponseRedirect('%s/' % batch.id)
		# Else fall through to re-render
	else:
		# Get request means we render an empty form
		form = PrepaidCreateForm()

	return render_to_response('confreg/prepaid_create_form.html', {
			'form': form,
			}, context_instance=RequestContext(request))

@login_required
@transaction.atomic
def viewvouchers(request, batchid):
	# View existing prepaid vouchers

	# WARNING! THIS VIEW IS NOT RESTRICTED TO ADMINS!
	# The same view is also used by the person who bought the voucher!
	# therefor, we need to make very sure he has permission!
	userbatch = False
	if not request.user.has_module_perms('invoicemgr'):
		# Superusers and invoice managers gain access through the generic
		# permission. Anybody else can only view his/her own batches
		batch = PrepaidBatch.objects.get(pk=batchid)
		if batch.buyer != request.user:
			raise Http404()
		userbatch = True
	else:
		# User has direct permissions, just retrieve the batch
		batch = PrepaidBatch.objects.get(pk=batchid)
	# Done with permissions checks

	vouchers = batch.prepaidvoucher_set.all()

	vouchermailtext = template_to_string('confreg/mail/prepaid_vouchers.txt',{
		'batch': batch,
		'vouchers': vouchers,
		})

	return render_to_response('confreg/prepaid_create_list.html', {
			'batch': batch,
			'vouchers': vouchers,
			'userbatch': userbatch,
			'vouchermailtext': vouchermailtext,
			}, RequestContext(request))

@login_required
@transaction.atomic
@user_passes_test_or_error(lambda u: u.has_module_perms('invoicemgr'))
def emailvouchers(request, batchid):
	batch = PrepaidBatch.objects.get(pk=batchid)
	vouchers = batch.prepaidvoucher_set.all()

	send_template_mail(batch.conference.contactaddr,
					   batch.buyer.email,
					   "Attendee vouchers for %s" % batch.conference,
					   'confreg/mail/prepaid_vouchers.txt',
					   {
						   'batch': batch,
						   'vouchers': vouchers,
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
		autocancel_hours = [conference.invoice_autocancel_hours, ]
		allregs = []

		# Set up a savepoint for rolling back the counter of discount codes if necessary
		if confirmstep:
			savepoint = transaction.savepoint()

		for e in sorted(emails):
			regs = ConferenceRegistration.objects.filter(conference=conference, email__iexact=e)
			if len(regs) == 1:
				allregs.append(regs[0])
				if regs[0].payconfirmedat:
					state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'Email not found or registration already completed.'})
					errors=1
				elif regs[0].invoice:
					state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'This registration already has an invoice generated for individual payment.'})
					errors=1
				elif regs[0].bulkpayment:
					state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'This registration is already part of a different bulk registration.'})
					errors=1
				elif not (regs[0].regtype and regs[0].regtype.active):
					state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'Registration type for this registration is not active!'})
					errors=1
				elif regs[0].vouchercode and not DiscountCode.objects.filter(code=regs[0].vouchercode, conference=regs[0].conference).exists():
					# Discount codes should still be allowed, just not full vouchers
					state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'Registration has a voucher code entered, and cannot be used for bulk payments.'})
					errors=1
				else:
					# If this is the confirmation step, we flag vouchers as used
					regrows = invoicerows_for_registration(regs[0], confirmstep)
					s = sum([r[1]*r[2] for r in regrows])
					if s == 0:
						# No payment needed
						state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'Registration type does not need payment'})
						errors=1
					else:
						# Normal registration. Check if discount code is valid, and then add it.
						if regs[0].vouchercode:
							dc = DiscountCode.objects.get(code=regs[0].vouchercode, conference=regs[0].conference)
							if dc.is_invoiced:
								state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'Registration uses discount code {0} which is not valid.'.format(dc.code)})
								errors=1
							elif dc.validuntil and dc.validuntil < date.today():
								state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'Registration uses discount code {0} which has expired.'.format(dc.code)})
								errors=1
							elif dc.maxuses > 0 and dc.registrations.count() >= dc.maxuses:
								state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'Registration uses discount code {0} which does not have enough remaining instances.'.format(dc.code)})
								errors=1
							# Else discount code is fine, so fall through
						if errors == 0:
							state.append({'email': regs[0].email, 'found': 1, 'pay': 1, 'total': s, 'rows':[u'%s (%s%s)' % (r[0], settings.CURRENCY_SYMBOL.decode('utf8'), r[2]) for r in regrows]})
							totalcost += s
							invoicerows.extend(regrows)
			else:
				state.append({'email': e, 'found': 0, 'text': 'Email not found or registration already completed.'})
				errors=1

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
					bp = BulkPayment()
					bp.user = request.user
					bp.conference = conference
					bp.numregs = len(allregs)
					bp.save() # Save so we get a primary key

					# Now assign this bulk record to all our registrations
					for r in allregs:
						r.bulkpayment = bp
						r.save()
						# Yes this is ugly and could be more efficient, but
						# this will do for now.
						autocancel_hours.append(r.regtype.invoice_autocancel_hours)
						autocancel_hours.extend([a.invoice_autocancel_hours for a in r.additionaloptions.filter(invoice_autocancel_hours__isnull=False)])

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

					# Finally, create an invoice for it
					manager = InvoiceManager()
					processor = InvoiceProcessor.objects.get(processorname="confreg bulk processor")

					bp.invoice = manager.create_invoice(
						request.user,
						request.user.email,
						form.data['recipient_name'],
						form.data['recipient_address'],
						"%s bulk registrations" % conference.conferencename,
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

#
# Handle unscheduled sessions, with a little app to make them scheduled
#
class EmptySpeaker(object):
	def all(self):
		return ['']
class SessionSlot(object):
	def __init__(self, room, slot):
		self.room = room
		self.starttime = slot.starttime
		self.endtime = slot.endtime
		# completely faked data
		self.track = 'unscheduled'
		self.cross_schedule = False
		self.id = room.id * 1000000 + slot.id
		self.title = ''
		self.speaker = EmptySpeaker()
class UnscheduledSession(object):
	def __init__(self, session, n):
		self.id = session.id
		self.title = session.title
		self.speaker_list = session.speaker_list
		self.track = session.track
		self.top = (n+1) * 75
		self.height = 50 * 1.5 # 50 minute slots hardcoded. nice...
		self.ispending = (session.status == 3)


@login_required
@transaction.atomic
def talkvote(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.talkvoters.filter(pk=request.user.id):
		raise Http404('You are not a talk voter for this conference!')

	isadmin = conference.administrators.filter(pk=request.user.id).exists()

	curs = connection.cursor()

	if request.method=='POST':
		# Record votes
		# We could probably do this with some fancy writable CTEs, but
		# this code won't run often, so we don't really care about being
		# fast, and this is easier...
		# Thus, remove existing entries and replace them with current ones.
		curs.execute("DELETE FROM confreg_conferencesessionvote WHERE voter_id=%(userid)s AND session_id IN (SELECT id FROM confreg_conferencesession WHERE conference_id=%(confid)s)", {
				'confid': conference.id,
				'userid': request.user.id,
				})
		curs.executemany("INSERT INTO confreg_conferencesessionvote (session_id, voter_id, vote, comment) VALUES (%(sid)s, %(vid)s, %(vote)s, %(comment)s)", [
				{
					'sid': k[3:],
					'vid': request.user.id,
					'vote': int(v) > 0 and int(v) or None,
					'comment': request.POST['tc_%s' % k[3:]],
					}
				for k,v in request.POST.items() if k.startswith("sv_") and (int(v)>0 or request.POST['tc_%s' % k[3:]])
				])

		return HttpResponseRedirect(".")

	order = ""
	if request.GET.has_key("sort"):
		if request.GET["sort"] == "avg":
			order = "avg DESC NULLS LAST,"

	# Render the form. Need to do this with a manual query, can't figure
	# out the right way to do it with the django ORM.
	curs.execute("SELECT s.id, s.title, s.status, s.lastnotifiedstatus, s.abstract, s.submissionnote, (SELECT string_agg(spk.fullname, ',') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers, (SELECT string_agg(spk.fullname || '(' || spk.company || ')', ',') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers_full, (SELECT string_agg('####' ||spk.fullname || '\n' || spk.abstract, '\n\n') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers_long, u.username, v.vote, v.comment, avg(v.vote) OVER (PARTITION BY s.id)::numeric(3,2) AS avg, trackname FROM (confreg_conferencesession s CROSS JOIN auth_user u) LEFT JOIN confreg_track track ON track.id=s.track_id LEFT JOIN confreg_conferencesessionvote v ON v.session_id=s.id AND v.voter_id=u.id WHERE s.conference_id=%(confid)s AND u.id IN (SELECT user_id FROM confreg_conference_talkvoters tv WHERE tv.conference_id=%(confid)s) ORDER BY " + order + "s.title,s.id, u.id=%(userid)s DESC, u.username", {
			'confid': conference.id,
			'userid': request.user.id,
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
	return render_to_response('confreg/sessionvotes.html', {
			'users': getusernames(all),
			'sessionvotes': transform(all),
			'conference': conference,
			'isadmin': isadmin,
		    'status_choices': STATUS_CHOICES,
			}, context_instance=RequestContext(request))

@login_required
@transaction.atomic
def talkvote_status(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.talkvoters.filter(pk=request.user.id):
		raise Http404('You are not a talk voter for this conference!')

	isadmin = conference.administrators.filter(pk=request.user.id).exists()
	if not isadmin:
		raise Http404('Only admins can change the status')

	if request.method!='POST':
		raise Http404('Can only use POST')

	session = get_object_or_404(ConferenceSession, conference=conference, id=request.POST['sessionid'])
	session.status = int(request.POST['newstatus'])
	session.save()
	return HttpResponse("{0};{1}".format(get_status_string(session.status),
										 session.status!=session.lastnotifiedstatus and 1 or 0,
									 ),	content_type='text/plain')

@login_required
@csrf_exempt
@transaction.atomic
def createschedule(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.talkvoters.filter(pk=request.user.id):
		if not request.user.is_superuser:
			raise Http404('You are not a talk voter for this conference!')


	if request.method=="POST":
		if request.POST.has_key('get'):
			# Get the current list of tentatively scheduled talks
			s = {}
			for sess in conference.conferencesession_set.all():
				if sess.tentativeroom != None and sess.tentativescheduleslot != None:
					s['slot%s' % ((sess.tentativeroom.id * 1000000) + sess.tentativescheduleslot.id)] = 'sess%s' % sess.id
			return HttpResponse(json.dumps(s), content_type="application/json")

		# Else we are saving
		if not request.user.is_superuser:
			raise Http404('Only superusers can save!')

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

	# We include *all* (non cross-schedule) sessions here, whether they
	# are approved or not.
	sessions = []
	for s in ConferenceSession.objects.filter(conference=conference, cross_schedule=False, status__in=(1,3)):
		sessions.append(UnscheduledSession(s, len(sessions)+1))


	daylist = ConferenceSessionScheduleSlot.objects.filter(conference=conference).dates('starttime', 'day')
	if len(daylist) == 0:
		return HttpResponse('No schedule slots defined for this conference, cannot create schedule yet.')
	rooms = Room.objects.filter(conference=conference)
	if len(rooms) == 0:
		return HttpResponse('No rooms defined for this conference, cannot create schedule yet.')
	tracks = Track.objects.filter(conference=conference).order_by('sortkey')

	days = []

	for d in daylist:
		slots = ConferenceSessionScheduleSlot.objects.filter(conference=conference, starttime__range=(d,d+timedelta(days=1)))

		# Generate a sessionset with the slots only, but with one slot for
		# each room when we have multiple rooms. Create a fake session that
		# just has enough for the wrapper to work.
		sessionset = SessionSet(conference.schedulewidth, conference.pixelsperminute)
		for s in slots:
			for r in rooms:
				sessionset.add(SessionSlot(r, s))
		sessionset.finalize()
		days.append({
				'day': d,
				'sessions': sessionset.all(),
				'rooms': sessionset.allrooms(),
				'schedule_height': sessionset.schedule_height(),
				'schedule_width': sessionset.schedule_width(),
				})
	return render_to_response('confreg/schedule_create.html', {
			'conference': conference,
			'days': days,
			'sessions': sessions,
			'tracks': tracks,
			'sesswidth': 600 / len(rooms),
			}, context_instance=RequestContext(request))

@login_required
@user_passes_test_or_error(lambda u: u.is_superuser)
def publishschedule(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

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
		return render_to_response('confreg/schedule_publish.html', {
				'done': 1,
			}, context_instance=RequestContext(request))
	else:
		transaction.rollback()
		return render_to_response('confreg/schedule_publish.html', {
				'changes': changes,
			}, context_instance=RequestContext(request))

@login_required
def reports(request, confname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confname)
	else:
		conference = get_object_or_404(Conference, urlname=confname, administrators=request.user)

	# Include information for the advanced reports
	from reports import attendee_report_fields, attendee_report_filters
	return render_to_response('confreg/reports.html', {
			'list': True,
			'additionaloptions': conference.conferenceadditionaloption_set.all(),
			'adv_fields': attendee_report_fields,
			'adv_filters': attendee_report_filters(conference),
		    }, context_instance=RequestContext(request))


@login_required
def advanced_report(request, confname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confname)
	else:
		conference = get_object_or_404(Conference, urlname=confname, administrators=request.user)

	if request.method != "POST":
		raise Http404()

	from reports import build_attendee_report

	return build_attendee_report(conference, request.POST )


@login_required
def simple_report(request, confname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confname)
	else:
		conference = get_object_or_404(Conference, urlname=confname, administrators=request.user)

	from reports import simple_reports

	if not simple_reports.has_key(request.GET['report']):
		raise Http404("Report not found")

	curs = connection.cursor()
	curs.execute(simple_reports[request.GET['report']], {
		'confid': conference.id,
		})
	d = curs.fetchall()
	collist = [dd[0] for dd in curs.description]
	# Get offsets of all columns that don't start with _
	colofs = [n for x,n in zip(collist, range(len(collist))) if not x.startswith('_')]
	if len(colofs) != len(collist):
		# One or more columns filtered - so filter the data
		d = map(itemgetter(*colofs), d)

	return render_to_response('confreg/simple_report.html', {
		'conference': conference,
		'columns': [dd for dd in collist if not dd.startswith('_')],
		'data': d,
	}, RequestContext(request))

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
			current.append(c)
		elif c.startdate > date.today():
			upcoming.append(c)
		else:
			past.append(c)

	return render_to_response('confreg/admin_dashboard.html', {
		'current': current,
		'upcoming': upcoming,
		'past': past,
	}, RequestContext(request))

@login_required
def admin_dashboard_single(request, urlname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=urlname)
	else:
		conference = get_object_or_404(Conference, urlname=urlname, administrators=request.user)

	return render_to_response('confreg/admin_dashboard_single.html', {
		'c': conference,
	}, RequestContext(request))

@login_required
def admin_registration_dashboard(request, urlname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=urlname)
	else:
		conference = get_object_or_404(Conference, urlname=urlname, administrators=request.user)

	curs = connection.cursor()

	tables = []

	# Registrations by reg type
	curs.execute("SELECT regtype, count(payconfirmedat) AS confirmed, count(r.id) FILTER (WHERE payconfirmedat IS NULL) AS unconfirmed, count(r.id) AS total FROM confreg_conferenceregistration r RIGHT JOIN confreg_registrationtype rt ON rt.id=r.regtype_id WHERE rt.conference_id={0} GROUP BY rt.id ORDER BY rt.sortkey".format(conference.id))
	tables.append({'title': 'Registration types',
				   'columns': ['Type', 'Confirmed', 'Unconfirmed', 'Total'],
				   'fixedcols': 1,
				   'rows': curs.fetchall()},)

	# Copy/paste string to get the reg status
	statusstr = "{0}, count(payconfirmedat) AS confirmed, count(r.id) FILTER (WHERE payconfirmedat IS NULL) AS unconfirmed, count(r.id) AS total, CASE WHEN {0} > 0 THEN {0}-count(r.id) ELSE NULL END AS remaining"

	# Additional options
	curs.execute("SELECT ao.name, {0} FROM confreg_conferenceregistration r INNER JOIN confreg_conferenceregistration_additionaloptions rao ON rao.conferenceregistration_id=r.id RIGHT JOIN confreg_conferenceadditionaloption ao ON ao.id=rao.conferenceadditionaloption_id WHERE ao.conference_id={1} GROUP BY ao.name, ao.maxcount ORDER BY ao.name".format(statusstr.format('ao.maxcount'), conference.id))
	tables.append({'title': 'Additional options',
				   'columns': ['Name', 'Max uses', 'Confirmed', 'Unconfirmed', 'Total', 'Remaining'],
				   'fixedcols': 1,
				   'rows': curs.fetchall()})

	# Discount codes
	curs.execute("SELECT code, validuntil, {0} FROM confreg_conferenceregistration r RIGHT JOIN confreg_discountcode dc ON dc.code=r.vouchercode WHERE dc.conference_id={1} AND (r.conference_id={1} OR r.conference_id IS NULL) GROUP BY dc.id ORDER BY code".format(statusstr.format('maxuses'), conference.id))
	tables.append({'title': 'Discount codes',
				   'columns': ['Code', 'Expires', 'Max uses', 'Confirmed', 'Unconfirmed','Total', 'Remaining'],
				   'fixedcols': 2,
				   'rows': curs.fetchall()})

	# Voucher batches
	curs.execute("SELECT b.buyername, s.name as sponsorname, count(v.user_id) AS used, count(*) FILTER (WHERE v.user_id IS NULL) AS unused, count(*) AS total FROM confreg_prepaidbatch b INNER JOIN confreg_prepaidvoucher v ON v.batch_id=b.id LEFT JOIN confreg_conferenceregistration r ON r.id=v.user_id LEFT JOIN confsponsor_sponsor s ON s.id = b.sponsor_id WHERE b.conference_id={0} GROUP BY b.id, s.name ORDER BY buyername".format(conference.id))
	tables.append({'title': 'Prepaid vouchers',
				   'columns': ['Buyer', 'Sponsor', 'Used', 'Unused', 'Total'],
				   'fixedcols': 2,
				   'rows': curs.fetchall()})

	# Add a sum row for eveything
	for t in tables:
		sums = ['Total']
		for cn in range(1, t['fixedcols']):
			sums.append('')
		for cn in range(t['fixedcols']-1, len(t['columns'])-1):
			sums.append(sum((r[cn+1] for r in t['rows'] if r[cn+1] != None)))
		t['rows'].append(sums)
	return render_to_response('confreg/admin_registration_dashboard.html', {
		'conference': conference,
		'tables': tables,
	}, RequestContext(request))

@login_required
@transaction.atomic
def admin_waitlist(request, urlname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=urlname)
	else:
		conference = get_object_or_404(Conference, urlname=urlname, administrators=request.user)

	if conference.attendees_before_waitlist <= 0:
		return render_to_response('confreg/admin_waitlist_inactive.html', {
			'conference': conference,
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
				wl.offerexpires = datetime.now() + timedelta(hours=form.cleaned_data['hours'])
				wl.save()
				RegistrationWaitlistHistory(waitlist=wl,
											text="Made offer valid for {0} hours by {1}".format(form.cleaned_data['hours'], request.user.username)).save()
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

	return render_to_response('confreg/admin_waitlist.html', {
		'conference': conference,
		'num_confirmedregs': num_confirmedregs,
		'num_invoicedregs': num_invoicedregs,
		'num_invoicedbulkpayregs': num_invoicedbulkpayregs,
		'num_waitlist_offered': num_waitlist_offered,
		'num_total': num_confirmedregs + num_invoicedregs + num_invoicedbulkpayregs + num_waitlist_offered,
		'waitlist': waitlist,
		'waitlist_cleared': waitlist_cleared,
		'form': form,
		}, RequestContext(request))

@login_required
@transaction.atomic
def admin_waitlist_cancel(request, urlname, wlid):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=urlname)
	else:
		conference = get_object_or_404(Conference, urlname=urlname, administrators=request.user)

	wl = get_object_or_404(RegistrationWaitlistEntry, pk=wlid, registration__conference=conference)
	reg = wl.registration
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


@login_required
@transaction.atomic
def admin_attendeemail(request, urlname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=urlname)
	else:
		conference = get_object_or_404(Conference, urlname=urlname, administrators=request.user)

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
				msgtxt = u"{0}\n\n-- \nThis message was sent to attendees of {1}.\nYou can view all communications for this conference at:\n{2}/events/register/{3}/\n".format(msg.message, conference, settings.SITEBASE, conference.urlname)
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

	return render_to_response('confreg/admin_mail.html', {
		'conference': conference,
		'mails': mails,
		'form': form,
	}, RequestContext(request))

@login_required
def admin_attendeemail_view(request, urlname, mailid):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=urlname)
	else:
		conference = get_object_or_404(Conference, urlname=urlname, administrators=request.user)

	mail = get_object_or_404(AttendeeMail, conference=conference, pk=mailid)

	return render_to_response('confreg/admin_mail_view.html', {
		'conference': conference,
		'mail': mail,
		'breadcrumbs': (('/events/admin/{0}/mail/'.format(conference.urlname), 'Attendee emails'), ),
		}, RequestContext(request))

@login_required
@transaction.atomic
def session_notify_queue(request, urlname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=urlname)
	else:
		conference = get_object_or_404(Conference, urlname=urlname, administrators=request.user)

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

	return render_to_response('confreg/admin_session_queue.html', {
		'conference': conference,
		'notifysessions': notifysessions,
		}, RequestContext(request))

@login_required
@transaction.atomic
def transfer_reg(request, urlname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=urlname)
	else:
		conference = get_object_or_404(Conference, urlname=urlname, administrators=request.user)

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

	return render_to_response('confreg/admin_transfer.html', {
		'conference': conference,
		'form': form,
		'steps': steps,
		'stephash': stephash,
	}, RequestContext(request))


# Send email to attendees of mixed conferences
@login_required
@user_passes_test_or_error(lambda u:u.is_superuser)
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
		q.write(" WHERE userid NOT IN (SELECT user_id FROM confreg_globaloptout)\n")
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

	return render_to_response('confreg/admin_cross_conference_mail.html', {
		'form': form,
		'recipients': recipients,
		'conferences': Conference.objects.all(),
		}, RequestContext(request))


@login_required
@user_passes_test_or_error(lambda u:u.is_superuser)
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
@login_required
@user_passes_test_or_error(lambda u: u.is_superuser)
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
	return render_to_response('confreg/admin_email.html', {
		'form': form,
		'recipientlist': ', '.join(recipients),
		}, RequestContext(request))


@login_required
@user_passes_test_or_error(lambda u: u.is_superuser)
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


	return render_to_response('confreg/admin_email.html', {
		'form': form,
		'recipientlist': ", ".join([s.name for s in speakers]),
		'whatfor': ", ".join(['Session "%s"' % s.title for s in sessions]),
		}, RequestContext(request))
