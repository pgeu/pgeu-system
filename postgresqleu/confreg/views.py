from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.template import RequestContext
from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings
from django.db import transaction, connection

from models import *
from forms import *

from datetime import datetime, timedelta
import base64
import re
import os
import sys
import imp
import csv

import simplejson as json

#
# The ConferenceContext allows overriding of the 'conftemplbase' variable,
# which is used to control the base template of all the confreg web pages.
# This allows a single conference to override the "framework" template
# around itself, while retaining all teh contents.
#
def ConferenceContext(request, conference):
	d = RequestContext(request)
	if conference and conference.template_override:
		conftemplbase = conference.template_override
	else:
		conftemplbase = "nav_events.html"
	d.update({
			'conftemplbase': conftemplbase,
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
		except Exception, ex:
			# Ignore problems, because we're lazy. Better render without the
			# data than not render at all.
			pass

	return d

@login_required
def home(request, confname):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.active:
		if not conference.testers.filter(pk=request.user.id):
			return render_to_response('confreg/closed.html', {
					'conference': conference,
			}, context_instance=ConferenceContext(request, conference))

	try:
		reg = ConferenceRegistration.objects.get(conference=conference,
			attendee=request.user)
	except:
		# No previous regisration, grab some data from the user profile
		reg = ConferenceRegistration(conference=conference, attendee=request.user)
		reg.email = request.user.email
		namepieces = request.user.first_name.rsplit(None,2)
		if len(namepieces) == 2:
			reg.firstname = namepieces[0]
			reg.lastname = namepieces[1]
		else:
			reg.firstname = request.user.first_name
		# If conference is set to autoapprove, then autoapprove
		if conference.autoapprove:
			reg.payconfirmedat = datetime.today()
			reg.payconfirmedby = 'auto'

	form_is_saved = False
	if request.method == 'POST':
		form = ConferenceRegistrationForm(data=request.POST, instance=reg)
		if form.is_valid():
			reg = form.save(commit=False)
			reg.conference = conference
			reg.attendee = request.user
			reg.save()
			form.save_m2m()
			form_is_saved = True
	else:
		# This is just a get, so render the form
		form = ConferenceRegistrationForm(instance=reg)

	return render_to_response('confreg/regform.html', {
		'form': form,
		'form_is_saved': form_is_saved,
		'reg': reg,
		'conference': conference,
		'additionaloptions': conference.conferenceadditionaloption_set.all(),
		'costamount': reg.regtype and reg.regtype.cost or 0,
		'payoptions': [{'name': p.name, 'infotext': p.infotext.replace('{{regid}}', str(reg.id)), 'paypalrecip': p.paypalrecip} for p in conference.paymentoptions.all()],
	}, context_instance=ConferenceContext(request, conference))

def feedback_available(request):
	conferences = Conference.objects.filter(feedbackopen=True).order_by('startdate')
	return render_to_response('confreg/feedback_available.html', {
		'conferences': conferences,
	}, context_instance=RequestContext(request))

@login_required
def feedback(request, confname):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.feedbackopen:
		# Allow conference testers to override
		if not conference.testers.filter(pk=request.user.id):
			return render_to_response('confreg/feedbackclosed.html', {
					'conference': conference,
			}, context_instance=ConferenceContext(request, conference))
		else:
			is_conf_tester = True
	else:
		is_conf_tester = False

	# Figure out if the user is registered
	try:
		r = ConferenceRegistration.objects.get(conference=conference, attendee=request.user)
	except ConferenceRegistration.DoesNotExist, e:
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

	return render_to_response('confreg/feedback_index.html', {
		'sessions': sessions,
		'conference': conference,
		'is_tester': is_conf_tester,
	}, context_instance=ConferenceContext(request, conference))

@login_required
def feedback_session(request, confname, sessionid):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))
	# Room for optimization: don't get these as separate steps
	conference = get_object_or_404(Conference, urlname=confname)
	session = get_object_or_404(ConferenceSession, pk=sessionid, conference=conference, status=1)

	if not conference.feedbackopen:
		# Allow conference testers to override
		if not conference.testers.filter(pk=request.user.id):
			return render_to_response('confreg/feedbackclosed.html', {
					'conference': conference,
			}, context_instance=ConferenceContext(request, conference))
		else:
			is_conf_tester = True
	else:
		is_conf_tester = False

	if session.starttime > datetime.now() and not is_conf_tester:
		return render_to_response('confreg/feedbacknotyet.html', {
			'conference': conference,
			'session': session,
		}, context_instance=ConferenceContext(request, conference))

	try:
		feedback = ConferenceSessionFeedback.objects.get(conference=conference, session=session, attendee=request.user)
	except ConferenceSessionFeedback.DoesNotExist, e:
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

	return render_to_response('confreg/feedback.html', {
		'session': session,
		'form': form,
		'conference': conference,
	}, context_instance=ConferenceContext(request, conference))


@login_required
@transaction.commit_on_success
def feedback_conference(request, confname):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))

	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.feedbackopen:
		# Allow conference testers to override
		if not conference.testers.filter(pk=request.user.id):
			return render_to_response('confreg/feedbackclosed.html', {
					'conference': conference,
			}, context_instance=ConferenceContext(request, conference))
		else:
			is_conf_tester = True
	else:
		is_conf_tester = False

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

	return render_to_response('confreg/feedback_conference.html', {
		'session': session,
		'form': form,
		'conference': conference,
	}, context_instance=ConferenceContext(request, conference))


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
		# Re-sort the rooms based on name
		self.rooms = dict(zip([roomname for roomname in sorted(self.rooms.keys(), key=lambda r:r.roomname)], range(0,len(self.rooms))))

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
			return render_to_response('confreg/scheduleclosed.html', {
					'conference': conference,
			}, context_instance=ConferenceContext(request, conference))

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

	return render_to_response('confreg/schedule.html', {
		'conference': conference,
		'days': days,
		'tracks': tracks,
	}, context_instance=ConferenceContext(request, conference))

def sessionlist(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.sessionsactive:
		if not conference.testers.filter(pk=request.user.id):
			return render_to_response('confreg/sessionsclosed.html', {
					'conference': conference,
			}, context_instance=ConferenceContext(request, conference))

	sessions = ConferenceSession.objects.filter(conference=conference).filter(cross_schedule=False).filter(status=1).order_by('track__sortkey', 'track', 'title')
	return render_to_response('confreg/sessionlist.html', {
		'conference': conference,
		'sessions': sessions,
	}, context_instance=ConferenceContext(request, conference))

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
			return render_to_response('confreg/sessionsclosed.html', {
					'conference': conference,
			}, context_instance=ConferenceContext(request, conference))

	session = get_object_or_404(ConferenceSession, conference=conference, pk=sessionid, cross_schedule=False, status=1)
	return render_to_response('confreg/session.html', {
		'conference': conference,
		'session': session,
	}, context_instance=ConferenceContext(request, conference))

def speaker(request, confname, speakerid, junk=None):
	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.sessionsactive:
		if not conference.testers.filter(pk=request.user.id):
			return render_to_response('confreg/sessionsclosed.html', {
					'conference': conference,
			}, context_instance=ConferenceContext(request, conference))

	speaker = get_object_or_404(Speaker, pk=speakerid)
	sessions = ConferenceSession.objects.filter(conference=conference, speaker=speaker, cross_schedule=False, status=1).order_by('starttime')
	if len(sessions) < 1:
		raise Http404("Speaker has no sessions at this conference")
	return render_to_response('confreg/speaker.html', {
		'conference': conference,
		'speaker': speaker,
		'sessions': sessions,
	}, context_instance=ConferenceContext(request, conference))

def speakerphoto(request, speakerid):
	speakerphoto = get_object_or_404(Speaker_Photo, pk=speakerid)
	return HttpResponse(base64.b64decode(speakerphoto.photo), mimetype='image/jpg')

@login_required
def speakerprofile(request, confurlname=None):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))

	speaker = conferences = callforpapers = None
	try:
		speaker = get_object_or_404(Speaker, user=request.user)
		conferences = Conference.objects.filter(conferencesession__speaker=speaker).distinct()
		callforpapers = Conference.objects.filter(callforpapersopen=True)
	except Speaker.DoesNotExist:
		speaker = None
		conferences = []
		callforpapers = None
	except Exception, e:
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
		context = ConferenceContext(request,
									get_object_or_404(Conference, urlname=confurlname))
	else:
		context = ConferenceContext(request, None)
	return render_to_response('confreg/speakerprofile.html', {
			'speaker': speaker,
			'conferences': conferences,
			'callforpapers': callforpapers,
			'form': form,
	}, context_instance=context)

@login_required
def callforpapers(request, confname):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))

	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.callforpapersopen:
		raise Http404('This conference has no open call for papers')

	try:
		speaker = Speaker.objects.get(user=request.user)
		sessions = ConferenceSession.objects.filter(conference=conference, speaker=speaker)
	except Speaker.DoesNotExist:
		sessions = []

	return render_to_response('confreg/callforpapers.html', {
			'conference': conference,
			'sessions': sessions,
	}, context_instance=ConferenceContext(request, conference))

@login_required
@transaction.commit_on_success
def callforpapers_new(request, confname):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))

	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.callforpapersopen:
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

@login_required
def callforpapers_edit(request, confname, sessionid):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))


	conference = get_object_or_404(Conference, urlname=confname)
	if not conference.callforpapersopen:
		raise Http404('This conference has no open call for papers')

	# Find users speaker record (should always exist when we get this far)
	speaker = get_object_or_404(Speaker, user=request.user)

	# Find the session record (should always exist when we get this far)
	session = get_object_or_404(ConferenceSession, conference=conference,
								speaker=speaker, pk=sessionid)

	if request.method == 'POST':
		# Save it!
		form = CallForPapersForm(data=request.POST, instance=session)
		if form.is_valid():
			form.save()
			return HttpResponseRedirect("..")
	else:
		# GET --> render empty form
		form = CallForPapersForm(instance=session)

	return render_to_response('confreg/callforpapersform.html', {
			'form': form,
			'session': session,
			'conference': conference,
	}, context_instance=ConferenceContext(request, conference))


@login_required
@transaction.commit_on_success
def prepaid(request, confname, regid):
	# Pay with prepaid voucher
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))

	conference = get_object_or_404(Conference, urlname=confname)
	reg = get_object_or_404(ConferenceRegistration, id=regid, attendee=request.user, conference=conference)

	if request.method == 'POST':
		# Trying to make a payment - verify that the data is correct before
		# accepting the voucher.
		form = PrepaidForm(registration=reg, data=request.POST)
		if form.is_valid():
			# The form is valid, so let's confirm the registration
			form.voucher.user = reg
			form.voucher.usedate = datetime.now()
			form.voucher.save()
			reg.payconfirmedat = datetime.now()
			reg.payconfirmedby = "voucher"
			reg.save()
			return HttpResponseRedirect('../..')
		# Else fall-through and re-render the form
	else:
		# GET -> render form if not already paid
		if reg.payconfirmedat:
			return render_to_response('confreg/prepaid_already.html', {
					'conference': conference,
			}, context_instance=ConferenceContext(request, conference))
		# Not paid yet, so render a form for it
		form = PrepaidForm()

	return render_to_response('confreg/prepaid_form.html', {
			'form': form,
			'reg': reg,
			'conference': conference,
			}, context_instance=ConferenceContext(request, conference))

@login_required
@transaction.commit_on_success
@user_passes_test(lambda u: u.has_module_perms('invoicemgr'))
def createvouchers(request):
	# Creation of pre-paid vouchers for conference registrations
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))

	if request.method == 'POST':
		form = PrepaidCreateForm(data=request.POST)
		if form.is_valid():
			# All data is correct, create the vouchers
			# (by first creating a batch)

			conference = Conference.objects.get(pk=form.data['conference'])
			regtype = RegistrationType.objects.get(pk=form.data['regtype'], conference=conference)
			buyer = User.objects.get(pk=form.data['buyer'])

			batch = PrepaidBatch(conference=conference,
								 regtype=regtype,
								 buyer=buyer)
			batch.save()

			vouchers=[]
			for n in range(0, int(form.data['count'])):
				v = PrepaidVoucher(conference=conference,
								   vouchervalue=base64.b64encode(os.urandom(37)).rstrip('='),
								   batch=batch)
				v.save()
			return HttpResponseRedirect('%s/' % batch.id)
		# Else fall through to re-render
	else:
		# Get request means we render an empty form
		form = PrepaidCreateForm()

	return render_to_response('confreg/prepaid_create_form.html', {
			'form': form,
			}, context_instance=RequestContext(request))

@login_required
@transaction.commit_on_success
def viewvouchers(request, batchid):
	# View existing prepaid vouchers
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))

	# WARNING! THIS VIEW IS NOT RESTRICTED TO ADMINS!
	# The same view is also used by the person who bought the voucher!
	# therefor, we need to make very sure he has permission!
	if not request.user.has_module_perms('invoicemgr'):
		# Superusers and invoice managers gain access through the generic
		# permission. Anybody else can only view his/her own batches
		batch = PrepaidBatch.objects.get(pk=batchid)
		if batch.buyer != request.user:
			raise Http404()
	else:
		# User has direct permissions, just retrieve the batch
		batch = PrepaidBatch.objects.get(pk=batchid)
	# Done with permissions checks

	vouchers = batch.prepaidvoucher_set.all()

	return render_to_response('confreg/prepaid_create_list.html', {
			'batch': batch,
			'vouchers': vouchers,
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
		self.track = session.track
		self.top = (n+1) * 75
		self.height = 50 * 1.5 # 50 minute slots hardcoded. nice...


@login_required
@transaction.commit_on_success
def talkvote(request, confname):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))
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
	curs.execute("SELECT s.id, s.title, s.status, s.abstract, s.submissionnote, (SELECT string_agg(spk.fullname, ',') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers, (SELECT string_agg(spk.fullname || '(' || spk.company || ')', ',') FROM confreg_speaker spk INNER JOIN confreg_conferencesession_speaker cs ON cs.speaker_id=spk.id WHERE cs.conferencesession_id=s.id) AS speakers_full, u.username, v.vote, v.comment, avg(v.vote) OVER (PARTITION BY s.id)::numeric(3,2) AS avg, trackname FROM (confreg_conferencesession s CROSS JOIN auth_user u) LEFT JOIN confreg_track track ON track.id=s.track_id LEFT JOIN confreg_conferencesessionvote v ON v.session_id=s.id AND v.voter_id=u.id WHERE s.conference_id=%(confid)s AND u.id IN (SELECT user_id FROM confreg_conference_talkvoters tv WHERE tv.conference_id=%(confid)s) ORDER BY " + order + "s.title,s.id, u.id=%(userid)s DESC, u.username", {
			'confid': conference.id,
			'userid': request.user.id,
			})
	col_names = [desc[0] for desc in curs.description]

	def getusernames(all):
		firstid = all[0][0]
		for id, title, status, abstract, submissionnote, speakers, speakers_full, username, vote, comment, avgvote, track in all:
			if id != firstid:
				return
			yield username

	def transform(all):
		lastid = -1
		rd = {}
		for id, title, status, abstract, submissionnote, speakers, speakers_full, username, vote, comment, avgvote, track in all:
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

@login_required
@transaction.commit_on_success
@user_passes_test(lambda u: u.is_superuser)
def createschedule(request, confname):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))
	conference = get_object_or_404(Conference, urlname=confname)

	if request.method=="POST":
		if request.POST.has_key('get'):
			# Get the current list of tentatively scheduled talks
			s = {}
			for sess in conference.conferencesession_set.all():
				if sess.tentativeroom != None and sess.tentativescheduleslot != None:
					s['slot%s' % ((sess.tentativeroom.id * 1000000) + sess.tentativescheduleslot.id)] = 'sess%s' % sess.id
			return HttpResponse(json.dumps(s), content_type="application/json")
		# Else we are saving

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
	for s in ConferenceSession.objects.filter(conference=conference, cross_schedule=False, status=1):
		sessions.append(UnscheduledSession(s, len(sessions)+1))


	daylist = ConferenceSessionScheduleSlot.objects.filter(conference=conference).dates('starttime', 'day')
	rooms = Room.objects.filter(conference=conference)
	tracks = Track.objects.filter(conference=conference).order_by('sortkey')

	days = []

	for d in daylist:
		slots = ConferenceSessionScheduleSlot.objects.filter(conference=conference, starttime__range=(d,d+timedelta(hours=23,minutes=59,seconds=59)))

		# Generate a sessionset with the slots only, but with one slot for
		# each room when we have multiple rooms. Create a fake session that
		# just has enough for the wrapper to work.
		sessionset = SessionSet(conference.schedulewidth, conference.pixelsperminute)
		n = 0
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
@transaction.commit_manually
@user_passes_test(lambda u: u.is_superuser)
def publishschedule(request, confname):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))
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

@login_required
def reports(request, confname):
	if request.user.is_superuser:
		conference = get_object_or_404(Conference, urlname=confname)
	else:
		conference = get_object_or_404(Conference, urlname=confname, administrators=request.user)

	if request.method == "POST":
		report = request.POST['report']
		fmt = request.POST['format']

		curs = connection.cursor()

		if report == "attendees":
			reporttitle = "Attendees"
			curs.execute('SELECT lastname AS "Lastname", firstname AS "Firstname", email AS "E-mail", company AS "Company", nick AS "Nick", twittername AS "Twitter", regtype AS "Registration type" FROM confreg_conferenceregistration cr INNER JOIN confreg_registrationtype rt ON rt.id=regtype_id WHERE cr.conference_id=%(id)s AND payconfirmedat IS NOT NULL ORDER BY regtype, lastname, firstname', {'id': conference.id})
		elif report == "attendees_unpaid":
			reporttitle = "Attendees (unpaid)"
			curs.execute('SELECT lastname AS "Lastname", firstname AS "Firstname", email AS "E-mail", company AS "Company", nick AS "Nick", twittername AS "Twitter", regtype AS "Registration type" FROM confreg_conferenceregistration cr INNER JOIN confreg_registrationtype rt ON rt.id=regtype_id WHERE cr.conference_id=%(id)s AND payconfirmedat IS NULL ORDER BY regtype, lastname, firstname', {'id': conference.id})
		elif report.startswith("ao"):
			m = re.match('^ao(\d+)$', report)
			if not m: raise Http404("Report does not exist")
			ao = ConferenceAdditionalOption.objects.get(conference=conference, id=m.group(1))
			reporttitle = "Attendees for %s" % ao.name
			curs.execute('SELECT lastname AS "Lastname", firstname AS "Firstname", email AS "E-mail", address AS "Address", country.name AS "Country", company AS "Company", phone AS "Phone" FROM confreg_conferenceregistration r LEFT JOIN country ON country.iso=country_id WHERE payconfirmedat IS NOT NULL AND EXISTS (SELECT * FROM confreg_conferenceregistration_additionaloptions a WHERE conferenceadditionaloption_id=%(aoid)s AND conferenceregistration_id=r.id) ORDER BY lastname, firstname', {'aoid': ao.id})
		else:
			raise Http404("Report does not exist")

		# We will buffer this in RAM - it's small enough
		data = curs.fetchall()

		# Render the correct output
		if fmt == "html":
			return render_to_response('confreg/reports.html', {
					'data': data,
					'header': [c[0] for c in curs.description],
					'reporttitle': reporttitle,
					}, context_instance=RequestContext(request))
		elif fmt == "csv":
			response = HttpResponse(mimetype='text/plain')
			writer = csv.writer(response, delimiter=';')
			writer.writerow([c[0] for c in curs.description])
			for row in data:
				writer.writerow([c.encode("utf-8") for c in row])
			return response
		else:
			raise Http404("Format does not exist")
	return render_to_response('confreg/reports.html', {
			'list': True,
			'additionaloptions': conference.conferenceadditionaloption_set.all(),
		    }, context_instance=RequestContext(request))
