from django.shortcuts import render_to_response, get_object_or_404
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.template import RequestContext
from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings

from models import *
from forms import *

from datetime import datetime, timedelta
import base64

@login_required
def home(request, confname):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))
	conference = get_object_or_404(Conference, urlname=confname)

	if not conference.active:
		return render_to_response('confreg/closed.html', {
			'conference': conference,
		})

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
	}, context_instance=RequestContext(request))

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
		return render_to_response('confreg/feedbackclosed.html', {
			'conference': conference,
		})

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
	sessions = ConferenceSession.objects.select_related().filter(conference=conference).filter(can_feedback=True).filter(starttime__lte=datetime.now())
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
	}, context_instance=RequestContext(request))

@login_required
def feedback_session(request, confname, sessionid):
	if settings.FORCE_SECURE_FORMS and not request.is_secure():
		return HttpResponseRedirect(request.build_absolute_uri().replace('http://','https://',1))
	# Room for optimization: don't get these as separate steps
	conference = get_object_or_404(Conference, urlname=confname)
	session = get_object_or_404(ConferenceSession, pk=sessionid, conference=conference)

	if not conference.feedbackopen:
		return render_to_response('confreg/feedbackclosed.html', {
			'conference': conference,
		})

	if session.starttime > datetime.now():
		return render_to_response('confreg/feedbacknotyet.html', {
			'conference': conference,
			'session': session,
		})

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
	}, context_instance=RequestContext(request))

class SessionSet(object):
	def __init__(self):
		self.headersize = 30
		self.rooms = {}
		self.tracks = {}
		self.sessions = []
		self.firsttime = datetime(2999,1,1)
		self.lasttime = datetime(1970,1,1)

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
		return int(600/len(self.rooms))

	def timediff_to_y_pixels(self, t, compareto):
		return ((t - compareto).seconds/60)*1.5

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
	daylist = ConferenceSession.objects.filter(conference=conference).dates('starttime', 'day')
	days = []
	tracks = {}
	for d in daylist:
		sessions = ConferenceSession.objects.select_related('track','room','speaker').filter(conference=conference,starttime__range=(d,d+timedelta(hours=23,minutes=59,seconds=59))).order_by('starttime','room__roomname')
		sessionset = SessionSet()
		for s in sessions: sessionset.add(s)
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
	}, context_instance=RequestContext(request))

def schedule_ical(request, confname):
	conference = get_object_or_404(Conference, urlname=confname)
	sessions = ConferenceSession.objects.filter(conference=conference).filter(cross_schedule=False).order_by('starttime')
	return render_to_response('confreg/schedule.ical', {
		'conference': conference,
		'sessions': sessions,
		'servername': request.META['SERVER_NAME'],
	}, mimetype='text/calendar', context_instance=RequestContext(request))

def session(request, confname, sessionid, junk=None):
	conference = get_object_or_404(Conference, urlname=confname)
	session = get_object_or_404(ConferenceSession, conference=conference, pk=sessionid, cross_schedule=False)
	return render_to_response('confreg/session.html', {
		'conference': conference,
		'session': session,
	}, context_instance=RequestContext(request))

def speaker(request, confname, speakerid, junk=None):
	conference = get_object_or_404(Conference, urlname=confname)
	speaker = get_object_or_404(Speaker, pk=speakerid)
	sessions = ConferenceSession.objects.filter(conference=conference, speaker=speaker, cross_schedule=False).order_by('starttime')
	if len(sessions) < 1:
		raise Http404("Speaker has no sessions at this conference")
	return render_to_response('confreg/speaker.html', {
		'conference': conference,
		'speaker': speaker,
		'sessions': sessions,
	}, context_instance=RequestContext(request))

def speakerphoto(request, speakerid):
	speakerphoto = get_object_or_404(Speaker_Photo, pk=speakerid)
	return HttpResponse(base64.b64decode(speakerphoto.photo), mimetype='image/jpg')

@login_required
def speakerprofile(request):
	speaker = get_object_or_404(Speaker, user=request.user)
	conferences = Conference.objects.filter(conferencesession__speaker=speaker).distinct()

	if request.method=='POST':
		# Attempt to save
		form = SpeakerProfileForm(data=request.POST, files=request.FILES, instance=speaker)
		if form.is_valid():
			if request.FILES.has_key('photo'):
				raise Exception("Deal with the file!")
			form.save()
			return HttpResponseRedirect('.')
	else:
		form = SpeakerProfileForm(instance=speaker)

	return render_to_response('confreg/speakerprofile.html', {
			'speaker': speaker,
			'conferences': conferences,
			'form': form,
	}, context_instance=RequestContext(request))
