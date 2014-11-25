#!/usr/bin/env python
# -*- coding: utf-8 -*-
from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.template import RequestContext, Context
from django.template.loaders.filesystem import _loader as filesystem_template_loader
from django.template.loader import get_template
from django.template.base import TemplateDoesNotExist
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.conf import settings
from django.db import transaction, connection

from models import Conference, ConferenceRegistration, ConferenceSession
from models import ConferenceSessionFeedback, Speaker, Speaker_Photo
from models import ConferenceFeedbackQuestion, ConferenceFeedbackAnswer
from models import RegistrationType, PrepaidVoucher, PrepaidBatch
from models import BulkPayment, Room, Track, ConferenceSessionScheduleSlot
from forms import ConferenceRegistrationForm, ConferenceSessionFeedbackForm
from forms import ConferenceFeedbackForm, SpeakerProfileForm
from forms import CallForPapersForm, BulkRegistrationForm
from forms import PrepaidCreateForm
from forms import EmailSendForm, EmailSessionForm
from util import invoicerows_for_registration

from models import get_status_string
from regtypes import confirm_special_reg_type

from postgresqleu.util.decorators import user_passes_test_or_error, ssl_required
from postgresqleu.invoices.models import Invoice, InvoicePaymentMethod, InvoiceRow
from postgresqleu.invoices.util import InvoiceManager, InvoicePresentationWrapper
from postgresqleu.invoices.models import InvoiceProcessor
from postgresqleu.mailqueue.util import send_mail, send_simple_mail

from datetime import datetime, timedelta
import base64
import re
import os
import sys
import imp
from email.mime.text import MIMEText

import simplejson as json

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
def render_conference_response(request, conference, templatename, dictionary=None):
	context = ConferenceContext(request, conference)
	if conference and conference.templateoverridedir:
		try:
			tmpl, display = filesystem_template_loader.load_template(templatename, (conference.templateoverridedir,))
			if dictionary:
				context.update(dictionary)
			return HttpResponse(tmpl.render(context))
		except TemplateDoesNotExist:
			# Template not found, so fall through to the default and load the template
			# from our main directory.
			pass

	# Either no override configured, or override not found
	return render_to_response(templatename, dictionary, context_instance=context)

@ssl_required
@login_required
@transaction.commit_on_success
def home(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.active:
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'confreg/closed.html')

	try:
		reg = ConferenceRegistration.objects.get(conference=conference,
			attendee=request.user)
	except:
		# No previous regisration, grab some data from the user profile
		reg = ConferenceRegistration(conference=conference, attendee=request.user)
		reg.email = request.user.email
		reg.firstname = request.user.first_name
		reg.lastname = request.user.last_name

	form_is_saved = False
	if request.method == 'POST':
		# Attempting to modify the registration
		if reg.bulkpayment:
			return render_conference_response(request, conference, 'confreg/bulkpayexists.html')
		if reg.invoice:
			return render_conference_response(request, conference, 'confreg/invoiceexists.html')

		form = ConferenceRegistrationForm(request.user, data=request.POST, instance=reg)
		if form.is_valid():
			reg = form.save(commit=False)
			reg.conference = conference
			reg.attendee = request.user
			reg.save()
			form.save_m2m()
			form_is_saved = True

			# Figure out if the user clicked a "magic save button"
			if request.POST['submit'].find('finish registration') > 0:
				# Complete registration!
				return HttpResponseRedirect("confirm/")

			# Or did they click cancel?
			if request.POST['submit'].find('Cancel') >= 0:
				reg.delete()
				return HttpResponseRedirect("canceled/")

			# Else it was a general save, and we'll fall through and
			# show the form again so details can be edited.
	else:
		# This is just a get. Depending on the state of the registration,
		# we may want to show the form or not.
		if reg.payconfirmedat or reg.invoice or reg.bulkpayment:
			# This registration can't be changed at this point
			return render_conference_response(request, conference, 'confreg/regform_completed.html', {
				'reg': reg,
				'invoice': InvoicePresentationWrapper(reg.invoice, "%s/events/register/%s/" % (settings.SITEBASE_SSL, conference.urlname)),
			})

		# Else fall through and render the form
		form = ConferenceRegistrationForm(request.user, instance=reg)

	return render_conference_response(request, conference, 'confreg/regform.html', {
		'form': form,
		'form_is_saved': form_is_saved,
		'reg': reg,
		'invoice': InvoicePresentationWrapper(reg.invoice, "%s/events/register/%s/" % (settings.SITEBASE_SSL, conference.urlname)),
		'additionaloptions': conference.conferenceadditionaloption_set.all(),
		'costamount': reg.regtype and reg.regtype.cost or 0,
	})

def feedback_available(request):
	conferences = Conference.objects.filter(feedbackopen=True).order_by('startdate')
	return render_to_response('confreg/feedback_available.html', {
		'conferences': conferences,
	}, context_instance=RequestContext(request))

@ssl_required
@login_required
def feedback(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.feedbackopen:
		# Allow conference testers to override
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'confreg/feedbackclosed.html')
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
			s.has_feedback = True

	return render_conference_response(request, conference, 'confreg/feedback_index.html', {
		'sessions': sessions,
		'is_tester': is_conf_tester,
	})

@ssl_required
@login_required
def feedback_session(request, confname, sessionid):
	# Room for optimization: don't get these as separate steps
	conference = get_object_or_404(Conference, urlname=confname)
	session = get_object_or_404(ConferenceSession, pk=sessionid, conference=conference, status=1)

	if not conference.feedbackopen:
		# Allow conference testers to override
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'confreg/feedbackclosed.html')
		else:
			is_conf_tester = True
	else:
		is_conf_tester = False

	if session.starttime > datetime.now() and not is_conf_tester:
		return render_conference_response(request, conference, 'confreg/feedbacknotyet.html', {
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

	return render_conference_response(request, conference, 'confreg/feedback.html', {
		'session': session,
		'form': form,
	})


@ssl_required
@login_required
@transaction.commit_on_success
def feedback_conference(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.feedbackopen:
		# Allow conference testers to override
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'confreg/feedbackclosed.html')

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

	return render_conference_response(request, conference, 'confreg/feedback_conference.html', {
		'session': session,
		'form': form,
	})


class SessionSet(object):
	def __init__(self, totalwidth, pixelsperminute):
		self.headersize = 30
		self.rooms = {}
		self.tracks = {}
		self.sessions = []
		self.firsttime = datetime(2999,1,1)
		self.lasttime = datetime(1970,1,1)
		self.totalwidth = totalwidth
		self.pixelsperminute = pixelsperminute

	def add(self, session):
		if not self.rooms.has_key(session.room):
			if not session.cross_schedule:
				self.rooms[session.room] = len(self.rooms)
		if not self.tracks.has_key(session.track):
			self.tracks[session.track] = session.track
		if session.starttime < self.firsttime:
			self.firsttime = session.starttime
		if session.endtime > self.lasttime:
			self.lasttime = session.endtime
		self.sessions.append(session)

	def finalize(self):
		# Re-sort the rooms based on sortkey and name
		self.rooms = dict(zip([roomname for roomname in sorted(self.rooms.keys(), key=lambda r:(r.sortkey, r.roomname))], range(0,len(self.rooms))))

	def all(self):
		for s in self.sessions:
			if not s.cross_schedule:
				yield {
					'id': s.id,
					'title': s.title,
					'speakers': s.speaker.all(),
					'timeslot': "%s - %s" % (s.starttime.strftime("%H:%M"), s.endtime.strftime("%H:%M")),
					'track': s.track,
					'leftpos': self.roomwidth()*self.rooms[s.room],
					'toppos': self.timediff_to_y_pixels(s.starttime, self.firsttime)+self.headersize,
					'widthpos': self.roomwidth()-2,
					'heightpos': self.timediff_to_y_pixels(s.endtime, s.starttime),
				}
			else:
				yield {
					'title': s.title,
					'timeslot': "%s - %s" % (s.starttime.strftime("%H:%M"), s.endtime.strftime("%H:%M")),
					'track': s.track,
					'leftpos': 0,
					'toppos': self.timediff_to_y_pixels(s.starttime, self.firsttime)+self.headersize,
					'widthpos': self.roomwidth() * len(self.rooms) - 2,
					'heightpos': self.timediff_to_y_pixels(s.endtime, s.starttime)-2,
				}

	def schedule_height(self):
		return self.timediff_to_y_pixels(self.lasttime, self.firsttime)+2+self.headersize

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

	def alltracks(self):
		return self.tracks

	def allrooms(self):
		return [{
			'name': r.roomname,
			'leftpos': self.roomwidth()*self.rooms[r],
			'widthpos': self.roomwidth()-2,
			'heightpos': self.headersize-2,
		} for r in self.rooms]

def schedule(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.scheduleactive:
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'confreg/scheduleclosed.html')

	daylist = ConferenceSession.objects.filter(conference=conference, status=1).dates('starttime', 'day')
	days = []
	tracks = {}
	for d in daylist:
		sessions = ConferenceSession.objects.select_related('track','room','speaker').filter(conference=conference,status=1,starttime__range=(d,d+timedelta(hours=23,minutes=59,seconds=59))).order_by('starttime','room__roomname')
		sessionset = SessionSet(conference.schedulewidth, conference.pixelsperminute)
		for s in sessions: sessionset.add(s)
		sessionset.finalize()
		days.append({
			'day': d,
			'sessions': sessionset.all(),
			'rooms': sessionset.allrooms(),
			'schedule_height': sessionset.schedule_height(),
			'schedule_width': sessionset.schedule_width(),
		})
		tracks.update(sessionset.alltracks())

	return render_conference_response(request, conference, 'confreg/schedule.html', {
		'days': days,
		'tracks': tracks,
	})

def sessionlist(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.sessionsactive:
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'confreg/sessionsclosed.html')

	sessions = ConferenceSession.objects.filter(conference=conference).filter(cross_schedule=False).filter(status=1).order_by('track__sortkey', 'track', 'title')
	return render_conference_response(request, conference, 'confreg/sessionlist.html', {
		'sessions': sessions,
	})

def schedule_ical(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.scheduleactive:
		# Not open. But we can't really render an error, so render a
		# completely empty sesison list instead
		sessions = None
	else:
		sessions = ConferenceSession.objects.filter(conference=conference).filter(cross_schedule=False).filter(status=1).filter(starttime__isnull=False).order_by('starttime')
	return render_to_response('confreg/schedule.ical', {
		'conference': conference,
		'sessions': sessions,
		'servername': request.META['SERVER_NAME'],
	}, mimetype='text/calendar', context_instance=RequestContext(request))

def session(request, confname, sessionid, junk=None):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.sessionsactive:
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'confreg/sessionsclosed.html')

	session = get_object_or_404(ConferenceSession, conference=conference, pk=sessionid, cross_schedule=False, status=1)
	return render_conference_response(request, conference, 'confreg/session.html', {
		'session': session,
	})

def speaker(request, confname, speakerid, junk=None):
	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.sessionsactive:
		if not conference.testers.filter(pk=request.user.id):
			return render_conference_response(request, conference, 'confreg/sessionsclosed.html')

	speaker = get_object_or_404(Speaker, pk=speakerid)
	sessions = ConferenceSession.objects.filter(conference=conference, speaker=speaker, cross_schedule=False, status=1).order_by('starttime')
	if len(sessions) < 1:
		raise Http404("Speaker has no sessions at this conference")
	return render_conference_response(request, conference, 'confreg/speaker.html', {
		'speaker': speaker,
		'sessions': sessions,
	})

def speakerphoto(request, speakerid):
	speakerphoto = get_object_or_404(Speaker_Photo, pk=speakerid)
	return HttpResponse(base64.b64decode(speakerphoto.photo), mimetype='image/jpg')

@ssl_required
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
	return render_conference_response(request, conf, 'confreg/speakerprofile.html', {
			'speaker': speaker,
			'conferences': conferences,
			'callforpapers': callforpapers,
			'form': form,
	})

@ssl_required
@login_required
def callforpapers(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	# This is called both for open and non-open call for papers, to let submitters view
	# when the schedule is not published. Thus, no check for callforpapersopen here.

	try:
		speaker = Speaker.objects.get(user=request.user)
		sessions = ConferenceSession.objects.filter(conference=conference, speaker=speaker)
	except Speaker.DoesNotExist:
		sessions = []

	return render_conference_response(request, conference, 'confreg/callforpapers.html', {
			'sessions': sessions,
			'is_tester': conference.testers.filter(pk=request.user.id).exists(),
	})

@ssl_required
@login_required
@transaction.commit_on_success
def callforpapers_new(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	is_tester = conference.testers.filter(pk=request.user.id).exists()
	if not conference.callforpapersopen and not is_tester:
		raise Http404('This conference has no open call for papers')

	if not request.POST.has_key('title'):
		raise Http404('Title not specified')
	if len(request.POST['title']) < 1:
		raise Http404('Title not specified')

	# Find the speaker, or create
	speaker, created = Speaker.objects.get_or_create(user=request.user)
	if created:
		speaker.fullname = request.user.first_name
		speaker.save()

	s = ConferenceSession(conference=conference,
						  title=request.POST['title'],
						  status=0,
						  initialsubmit=datetime.now())
	s.save()

	# Add speaker (must be saved before we can do that)
	s.speaker.add(speaker)
	s.save()

	# Redirect back
	return HttpResponseRedirect("../%s/" % s.id)

@ssl_required
@login_required
def callforpapers_edit(request, confname, sessionid):
	conference = get_object_or_404(Conference, urlname=confname)
	is_tester = conference.testers.filter(pk=request.user.id).exists()

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
		else:
			feedbackcount = 0
			feedbackdata = None
			feedbacktext = None

		return render_conference_response(request, conference, 'confreg/session_feedback.html', {
			'session': session,
			'feedbackcount': feedbackcount,
			'feedbackdata': feedbackdata,
			'feedbacktext': feedbacktext,
			'feedbackfields': [f.replace('_',' ').title() for f in feedback_fields],
			})


	if request.method == 'POST':
		# Save it!
		form = CallForPapersForm(data=request.POST, instance=session)
		if form.is_valid():
			form.save()
			return HttpResponseRedirect("..")
	else:
		# GET --> render empty form
		form = CallForPapersForm(instance=session)

	return render_conference_response(request, conference, 'confreg/callforpapersform.html', {
			'form': form,
			'session': session,
	})

@ssl_required
@login_required
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
		return render_conference_response(request, conference, 'confreg/callforpapersconfirmed.html', {
		'session': session,
	})

	if request.method == 'POST':
		if request.POST.has_key('is_confirmed') and request.POST['is_confirmed'] == '1':
			session.status = 1 # Now approved!
			session.save()

	return render_conference_response(request, conference, 'confreg/callforpapersconfirm.html', {
		'session': session,
	})

@ssl_required
@login_required
@transaction.commit_on_success
def confirmreg(request, confname):
	# Confirm a registration step. This will show the user the final
	# cost of the registration, minus any discounts found (including
	# complete-registration vouchers).
	conference = get_object_or_404(Conference, urlname=confname)
	reg = get_object_or_404(ConferenceRegistration, attendee=request.user, conference=conference)
	# This should never happen since we should error out in the form,
	# but make sure we don't accidentally proceed.
	if not reg.regtype:
		return render_conference_response(request, conference, 'confreg/noregtype.html')
	if reg.bulkpayment:
		return render_conference_response(request, conference, 'confreg/bulkpayexists.html')

	# If there is already an invoice, then this registration has
	# been processed already.
	if reg.invoice:
		return HttpResponseRedirect("/events/register/%s/" % conference.urlname)

	# See if the registration type blocks it
	s = confirm_special_reg_type(reg.regtype.specialtype, reg)
	if s:
		return render_conference_response(request, conference, 'confreg/specialregtypeconfirm.html', {
			'reason': s,
			})

	if request.method == 'POST':
		if request.POST['submit'].find('Back') >= 0:
			return HttpResponseRedirect("../")
		if request.POST['submit'].find('finish registration') >= 0:
			# Get the invoice rows and flag any vouchers as used
			# (committed at the end of the view so if something
			# goes wrong they automatically go back to unused)
			invoicerows = invoicerows_for_registration(reg, True)
			totalcost = sum([r[2] for r in invoicerows])

			if len(invoicerows) <= 0:
				return HttpResponseRedirect("../")

			if totalcost == 0:
				# Paid in total with vouchers, or completely free
				# registration type. So just flag the registration
				# as confirmed.
				reg.payconfirmedat = datetime.today()
				reg.payconfirmedby = "no payment reqd"
				reg.save()
				return HttpResponseRedirect("../")

			# Else there is a cost, so we create an invoice for that
			# cost. Registration will be confirmed when the invoice is paid.
			manager = InvoiceManager()
			processor = InvoiceProcessor.objects.get(processorname="confreg processor")
			reg.invoice = manager.create_invoice(
				request.user,
				request.user.email,
				reg.firstname + ' ' + reg.lastname,
				reg.company + "\n" + reg.address + "\n" + reg.country.name,
				"%s invoice for %s" % (conference.conferencename, reg.email),
				datetime.now(),
				datetime.now(),
				invoicerows,
				processor = processor,
				processorid = reg.pk,
				bankinfo = False,
				accounting_account = settings.ACCOUNTING_CONFREG_ACCOUNT,
				accounting_object = conference.accounting_object
			)

			reg.invoice.save()
			reg.save()
			return HttpResponseRedirect("../invoice/%s/" % reg.pk)

		# Else this is some random button we haven't heard of, so just
		# fall through and show the form again.

	# Figure out what should go on the invoice. Don't flag possible
	# vouchers as used, since confirmation isn't done yet.
	invoicerows = invoicerows_for_registration(reg, False)
	totalcost = sum([r[2] for r in invoicerows])

	# It should be impossible to end up with zero invoice rows, so just
	# redirect back if that happens
	if len(invoicerows) <= 0:
		return HttpResponseRedirect("../")

	return render_conference_response(request, conference, 'confreg/regform_confirm.html', {
		'invoicerows': invoicerows,
		'totalcost': totalcost,
		'regalert': reg.regtype.alertmessage,
		})


@ssl_required
@login_required
def cancelreg(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	return render_conference_response(request, conference, 'confreg/canceled.html')

@ssl_required
@login_required
@transaction.commit_on_success
def invoice(request, confname, regid):
	# Show the invoice. We do this in a separate view from the main view,
	# even though the invoice is present on the main view as well, in order
	# to make things even more obvious.
	# Assumes that the actual invoice has already been created!
	conference = get_object_or_404(Conference, urlname=confname)
	reg = get_object_or_404(ConferenceRegistration, id=regid, attendee=request.user, conference=conference)

	if reg.bulkpayment:
		return render_conference_response(request, conference, 'confreg/bulkpayexists.html')

	if not reg.invoice:
		# We should never get here if we don't have an invoice. If it does
		# happen, just redirect back.
		return HttpResponseRedirect('../../')

	return render_conference_response(request, conference, 'confreg/invoice.html', {
			'reg': reg,
			'invoice': reg.invoice,
			})

@ssl_required
@login_required
@transaction.commit_on_success
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
								  title='Prepaid vouchers for %s' % conference.conferencename,
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
													  rowamount=regtype.cost))
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

@ssl_required
@login_required
@transaction.commit_on_success
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

	vouchermailtext = get_template('confreg/mail/prepaid_vouchers.txt').render(Context({
		'batch': batch,
		'vouchers': vouchers,
		}))

	return render_to_response('confreg/prepaid_create_list.html', {
			'batch': batch,
			'vouchers': vouchers,
			'userbatch': userbatch,
			'vouchermailtext': vouchermailtext,
			})

@ssl_required
@login_required
@transaction.commit_on_success
@user_passes_test_or_error(lambda u: u.has_module_perms('invoicemgr'))
def emailvouchers(request, batchid):
	batch = PrepaidBatch.objects.get(pk=batchid)
	vouchers = batch.prepaidvoucher_set.all()

	vouchermailtext = get_template('confreg/mail/prepaid_vouchers.txt').render(Context({
		'batch': batch,
		'vouchers': vouchers,
	}))
	send_simple_mail(batch.conference.contactaddr,
					  batch.buyer.email,
					  "Attendee vouchers for %s" % batch.conference,
					  vouchermailtext,
					  )
	return HttpResponse('OK')

@ssl_required
@login_required
@transaction.commit_on_success
def bulkpay(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	bulkpayments = BulkPayment.objects.filter(conference=conference, user=request.user)

	if request.method == 'POST':
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
		for e in sorted(emails):
			regs = ConferenceRegistration.objects.filter(conference=conference, invoice=None, bulkpayment=None, payconfirmedat=None, email=e)
			if len(regs) == 1:
				allregs.append(regs[0])
				if not (regs[0].regtype and regs[0].regtype.active):
					state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'Registration type for this registration is not active!'})
					errors=1
				elif regs[0].vouchercode:
					state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'Registration has a voucher code entered, and cannot be used for bulk payments.'})
					errors=1
				else:
					regrows = invoicerows_for_registration(regs[0], False)
					s = sum([r[2] for r in regrows])
					if s == 0:
						# No payment needed
						state.append({'email': e, 'found': 1, 'pay': 0, 'text': 'Registration type does not need payment'})
						errors=1
					else:
						# Normal registration, so add it
						state.append({'email': e, 'found': 1, 'pay': 1, 'total': s, 'rows':[u'%s (%s%s)' % (r[0], settings.CURRENCY_SYMBOL.decode('utf8'), r[2]) for r in regrows]})
						totalcost += s
						invoicerows.extend(regrows)
			else:
				state.append({'email': e, 'found': 0, 'text': 'Email not found'})
				errors=1

		if request.POST['submit'] == 'Confirm above registrations and generate invoice':
			# Trying to finish things off, are we? :)
			if not errors:
				# Verify the total cost
				if int(request.POST['confirmed_total_cost']) != totalcost:
					messages.warning(request, 'Total cost changed, probably because somebody modified their registration during processing. Please verify the costs below, and retry.')
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

					# Finally, create an invoice for it
					manager = InvoiceManager()
					processor = InvoiceProcessor.objects.get(processorname="confreg bulk processor")

					bp.invoice = manager.create_invoice(
						request.user,
						request.user.email,
						form.data['recipient_name'],
						form.data['recipient_address'],
						"%s bulk payment" % conference.conferencename,
						datetime.now(),
						datetime.now(),
						invoicerows,
						processor=processor,
						processorid = bp.pk,
						bankinfo = False,
						accounting_account = settings.ACCOUNTING_CONFREG_ACCOUNT,
						accounting_object = conference.accounting_object,
					)
					bp.invoice.save()
					bp.save()

					return HttpResponseRedirect('%s/' % bp.pk)
			else:
				messages.warning(request, 'An error occurred processing the registrations, please review the email addresses on the list')

		return render_conference_response(request, conference, 'confreg/bulkpay_list.html', {
			'form': form,
			'email_list': email_list,
			'errors': errors,
			'totalcost': errors and -1 or totalcost,
			'state': state,
			'bulkpayments': bulkpayments,
			'currency_symbol': settings.CURRENCY_SYMBOL,
		})
	else:
		form = BulkRegistrationForm()
		return render_conference_response(request, conference, 'confreg/bulkpay_list.html', {
			'form': form,
			'bulkpayments': bulkpayments,
			'currency_symbol': settings.CURRENCY_SYMBOL,
		})


@ssl_required
@login_required
def bulkpay_view(request, confname, bulkpayid):
	conference = get_object_or_404(Conference, urlname=confname)

	bulkpayment = get_object_or_404(BulkPayment, conference=conference, user=request.user, pk=bulkpayid)

	return render_conference_response(request, conference, 'confreg/bulkpay_view.html', {
		'bulkpayment': bulkpayment,
		'invoice': bulkpayment.invoice,
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


@ssl_required
@login_required
@transaction.commit_on_success
def talkvote(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.talkvoters.filter(pk=request.user.id):
		raise Http404('You are not a talk voter for this conference!')

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
		transaction.set_dirty()
		return HttpResponseRedirect(".")

	order = ""
	if request.GET.has_key("sort"):
		if request.GET["sort"] == "avg":
			order = "avg DESC NULLS LAST,"

	# Render the form. Need to do this with a manual query, can't figure
	# out the right way to do it with the django ORM.
	curs.execute("SELECT s.id, s.title, s.status, s.abstract, s.submissionnote, (SELECT string_agg(spk.fullname, ',') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers, (SELECT string_agg(spk.fullname || '(' || spk.company || ')', ',') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers_full, (SELECT string_agg('####' ||spk.fullname || '\n' || spk.abstract, '\n\n') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers_long, u.username, v.vote, v.comment, avg(v.vote) OVER (PARTITION BY s.id)::numeric(3,2) AS avg, trackname FROM (confreg_conferencesession s CROSS JOIN auth_user u) LEFT JOIN confreg_track track ON track.id=s.track_id LEFT JOIN confreg_conferencesessionvote v ON v.session_id=s.id AND v.voter_id=u.id WHERE s.conference_id=%(confid)s AND u.id IN (SELECT user_id FROM confreg_conference_talkvoters tv WHERE tv.conference_id=%(confid)s) ORDER BY " + order + "s.title,s.id, u.id=%(userid)s DESC, u.username", {
			'confid': conference.id,
			'userid': request.user.id,
			})

	def getusernames(all):
		firstid = all[0][0]
		for id, title, status, abstract, submissionnote, speakers, speakers_full, speakers_long, username, vote, comment, avgvote, track in all:
			if id != firstid:
				return
			yield username

	def transform(all):
		lastid = -1
		rd = {}
		for id, title, status, abstract, submissionnote, speakers, speakers_full, speakers_long, username, vote, comment, avgvote, track in all:
			if id != lastid:
				if lastid != -1:
					yield rd
				rd = {
					'id': id,
					'title': title,
					'status': get_status_string(status),
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
			}, context_instance=RequestContext(request))

@ssl_required
@login_required
@transaction.commit_on_success
def createschedule(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.talkvoters.filter(pk=request.user.id):
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
		slots = ConferenceSessionScheduleSlot.objects.filter(conference=conference, starttime__range=(d,d+timedelta(hours=23,minutes=59,seconds=59)))

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

@ssl_required
@login_required
@transaction.commit_manually
@user_passes_test_or_error(lambda u: u.is_superuser)
def publishschedule(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

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

@ssl_required
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


@ssl_required
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


@ssl_required
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

	return render_to_response('confreg/simple_report.html', {
		'conference': conference,
		'columns': [d[0] for d in curs.description],
		'data': curs.fetchall(),
	})

@ssl_required
@login_required
def admin_dashboard(request):
	if request.user.is_superuser:
		conferences = Conference.objects.all().order_by('-startdate')
	else:
		conferences = Conference.objects.filter(administrators=request.user).order_by('-startdate')

	return render_to_response('confreg/admin_dashboard.html', {
		'conferences': conferences,
	})

# Admin view that's used to send email to multiple users
@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.is_superuser)
@transaction.commit_on_success
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
		})


@ssl_required
@login_required
@user_passes_test_or_error(lambda u: u.is_superuser)
@transaction.commit_on_success
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
		})
