from django.db import models
from django.contrib.auth.models import User
from django.conf import settings

from postgresqleu.confreg.dbimage import SpeakerImageStorage

import datetime
import pytz

from postgresqleu.countries.models import Country

class PaymentOption(models.Model):
	name = models.CharField(max_length=64, blank=False, null=False)
	infotext = models.TextField(blank=False, null=False)
	paypalrecip = models.EmailField(max_length=1024, null=True, blank=True)
	sortkey = models.IntegerField(null=False, blank=False)

	def __unicode__(self):
		return self.name

	class Meta:
		ordering = ['sortkey', ]

class Conference(models.Model):
	urlname = models.CharField(max_length=32, blank=False, null=False, unique=True)
	conferencename = models.CharField(max_length=64, blank=False, null=False)
	startdate = models.DateField(blank=False, null=False)
	enddate = models.DateField(blank=False, null=False)
	location = models.CharField(max_length=128, blank=False, null=False)
	contactaddr = models.EmailField(blank=False,null=False)
	paymentoptions = models.ManyToManyField(PaymentOption)
	active = models.BooleanField(blank=False,null=False,default=True)
	feedbackopen = models.BooleanField(blank=False,null=False,default=True)
	conferencefeedbackopen = models.BooleanField(blank=False,null=False,default=False)
	confurl = models.CharField(max_length=128, blank=False, null=False)
	listadminurl = models.CharField(max_length=128, blank=True, null=False)
	listadminpwd = models.CharField(max_length=128, blank=True, null=False)
	speakerlistadminurl = models.CharField(max_length=128, blank=True, null=False)
	speakerlistadminpwd = models.CharField(max_length=128, blank=True, null=False)
	administrators = models.ManyToManyField(User, null=False, blank=True)
	testers = models.ManyToManyField(User, null=False, blank=True, related_name="testers_set")
	asktshirt = models.BooleanField(blank=False, null=False, default=True)
	askfood = models.BooleanField(blank=False, null=False, default=True)
	autoapprove = models.BooleanField(blank=False, null=False, default=False)
	additionalintro = models.TextField(blank=True, null=False)
	basetemplate = models.CharField(max_length=128, blank=True, null=True, default=None)

	def __unicode__(self):
		return self.conferencename

	@property
	def conferencedatestr(self):
		if self.enddate and not self.startdate==self.enddate:
			return "%s - %s" % (
				self.startdate.strftime("%Y-%m-%d"),
				self.enddate.strftime("%Y-%m-%d")
			)
		else:
			return self.startdate.strftime("%Y-%m-%d")

	@property
	def template_override(self):
		if self.basetemplate and len(self.basetemplate) > 0:
			return self.basetemplate
		return None

class RegistrationType(models.Model):
	conference = models.ForeignKey(Conference, null=False)
	regtype = models.CharField(max_length=64, null=False, blank=False)
	cost = models.IntegerField(null=False)
	active = models.BooleanField(null=False, blank=False, default=True)
	inlist = models.BooleanField(null=False, blank=False, default=True)
	sortkey = models.IntegerField(null=False, blank=False, default=10)

	class Meta:
		ordering = ['conference', 'sortkey', ]

	def __unicode__(self):
		if self.cost == 0:
			return self.regtype
		else:
			return "%s (EUR %s)" % (self.regtype, self.cost)

	def is_registered_type(self):
		# Starts with * means "not attending"
		if self.regtype.startswith('*'): return False
		return True

	@property
	def stringcost(self):
		return str(self.cost)

class ShirtSize(models.Model):
        shirtsize = models.CharField(max_length=32)

        def __unicode__(self):
                return self.shirtsize

class ConferenceAdditionalOption(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	name = models.CharField(max_length=100, null=False, blank=False)
	cost = models.IntegerField(null=False)
	maxcount = models.IntegerField(null=False)

	class Meta:
		ordering = ['name', ]

	def __unicode__(self):
		# This is what renders in the multichoice checkboxes, so make
		# it nice for the end user.
		if self.cost > 0:
			coststr = " (EUR %s)" % self.cost
		else:
			coststr = ""
		if self.maxcount > 0:
			usedcount = self.conferenceregistration_set.count()
			return "%s%s (%s of %s available)" % (self.name, coststr,
												  self.maxcount - usedcount,
												  self.maxcount)
		return "%s%s" % (self.name, coststr)

class ConferenceRegistration(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	regtype = models.ForeignKey(RegistrationType, null=True, blank=True, verbose_name="Registration type")
	attendee = models.ForeignKey(User, null=False, blank=False)
	firstname = models.CharField(max_length=100, null=False, blank=False, verbose_name="First name")
	lastname = models.CharField(max_length=100, null=False, blank=False, verbose_name="Last name")
	email = models.EmailField(null=False, blank=False, verbose_name="E-mail address")
	company = models.CharField(max_length=100, null=False, blank=False, verbose_name="Company")
	address = models.TextField(max_length=200, null=False, blank=True, verbose_name="Address")
	country = models.ForeignKey(Country, null=False, blank=False, verbose_name="Country")
	phone = models.CharField(max_length=100, null=False, blank=True, verbose_name="Phone number")
	shirtsize = models.ForeignKey(ShirtSize, null=True, blank=True, verbose_name="Preferred T-shirt size")
	dietary = models.CharField(max_length=100, null=False, blank=True, verbose_name="Special dietary needs")
	additionaloptions = models.ManyToManyField(ConferenceAdditionalOption, null=False, blank=True, verbose_name="Additional options")

	# Admin fields!
	payconfirmedat = models.DateField(null=True, blank=True, verbose_name="Payment confirmed at")
	payconfirmedby = models.CharField(max_length=16, null=True, blank=True, verbose_name="Payment confirmed by")
	created = models.DateTimeField(null=False, blank=False, default=datetime.datetime.now, verbose_name="Registration created")

	# Access from templates requires properties
	@property
	def isregistered(self):
		if not self.regtype: return False
		return self.regtype.is_registered_type()

	@property
	def needspayment(self):
		if not self.regtype: return False
		if self.regtype.cost == 0: return False
		return True

	# For the admin interface (mainly)
	def __unicode__(self):
		return "%s: %s %s <%s>" % (self.conference, self.firstname, self.lastname, self.email)

class Track(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	trackname = models.CharField(max_length=100, null=False, blank=False)
	color = models.CharField(max_length=20, null=False, blank=True)

	def __unicode__(self):
		return "%s (%s)" % (self.trackname, self.conference)

class Room(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	roomname = models.CharField(max_length=20, null=False, blank=False)

	def __unicode__(self):
		return "%s (%s)" % (self.roomname, self.conference)


class Speaker(models.Model):
	def get_upload_path(instance, filename):
		return "%s" % instance.id

	user = models.ForeignKey(User, null=True, blank=True)
	fullname = models.CharField(max_length=100, null=False, blank=False)
	company = models.CharField(max_length=100, null=False, blank=True)
	abstract = models.TextField(null=False, blank=True)
	photofile = models.ImageField(upload_to=get_upload_path, storage=SpeakerImageStorage(), blank=True, null=True, verbose_name="Photo")


	@property
	def name(self):
		return self.fullname

	def has_abstract(self):
		return len(self.abstract)>0
	has_abstract.boolean = True

	def has_photo(self):
		return (self.photofile != None and self.photofile != "")
	has_photo.boolean= True

	def __unicode__(self):
		return self.name

	class Meta:
		ordering = ['fullname', ]

class Speaker_Photo(models.Model):
	speaker = models.ForeignKey(Speaker, db_column='id', primary_key=True)
	photo = models.TextField(null=False, blank=False)

	def __unicode__(self):
		return self.speaker.name

	def delete(self):
		# Remove reference from speaker, so we don't think the pic is there
		self.speaker.photofile = None
		self.speaker.save()
		super(Speaker_Photo, self).delete()

class ConferenceSession(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	speaker = models.ManyToManyField(Speaker)
	title = models.CharField(max_length=200, null=False, blank=False)
	starttime = models.DateTimeField(null=False, blank=False)
	endtime = models.DateTimeField(null=True)
	track = models.ForeignKey(Track, null=True, blank=True)
	room = models.ForeignKey(Room, null=True, blank=True)
	cross_schedule = models.BooleanField(null=False, default=False)
	can_feedback = models.BooleanField(null=False, default=True)
	abstract = models.TextField(null=False, blank=True)

	# Not a db field, but set from the view to track if the current user
	# has given any feedback on this session.
	has_feedback = False

	@property
	def speaker_list(self):
		return ", ".join([s.name for s in self.speaker.all()])

	def __unicode__(self):
		return "%s: %s (%s)" % (
			self.speaker_list,
			self.title,
			self.starttime,
		)

	@property
	def shorttitle(self):
		return "%s (%s)" % (
			self.title,
			self.starttime,
		)

	@property
	def utcstarttime(self):
		return self._utc_time(self.starttime)

	@property
	def utcendtime(self):
		return self._utc_time(self.endtime)

	def _utc_time(self, time):
		if not hasattr(self, '_localtz'):
			self._localtz = pytz.timezone(settings.TIME_ZONE)
		return self._localtz.localize(time).astimezone(pytz.utc)

	class Meta:
		ordering = [ 'starttime', ]

class ConferenceSessionFeedback(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	session = models.ForeignKey(ConferenceSession, null=False, blank=False)
	attendee = models.ForeignKey(User, null=False, blank=False)
	topic_importance = models.IntegerField(null=False, blank=False)
	content_quality = models.IntegerField(null=False, blank=False)
	speaker_knowledge = models.IntegerField(null=False, blank=False)
	speaker_quality = models.IntegerField(null=False, blank=False)
	speaker_feedback = models.TextField(null=False, blank=True, verbose_name='Comments to the speaker')
	conference_feedback = models.TextField(null=False, blank=True, verbose_name='Comments to the conference organizers')

	def __unicode__(self):
		return unicode("%s - %s (%s)") % (self.conference, self.session, self.attendee)

class ConferenceFeedbackQuestion(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	question = models.CharField(max_length=100, null=False, blank=False)
	isfreetext = models.BooleanField(blank=False, null=False, default=False)
	textchoices = models.CharField(max_length=500, null=False, blank=True)
	sortkey = models.IntegerField(null=False, default=100)
	newfieldset = models.CharField(max_length=100, null=False, blank=True)

	def __unicode__(self):
		return "%s: %s" % (self.conference, self.question)

	class Meta:
		ordering = ['conference', 'sortkey', ]

class ConferenceFeedbackAnswer(models.Model):
	conference = models.ForeignKey(Conference, null=False, blank=False)
	question = models.ForeignKey(ConferenceFeedbackQuestion, null=False, blank=False)
	attendee = models.ForeignKey(User, null=False, blank=False)
	rateanswer = models.IntegerField(null=True)
	textanswer = models.TextField(null=False, blank=True)

	def __unicode__(self):
		return "%s - %s: %s" % (self.conference, self.attendee, self.question.question)

	class Meta:
		ordering = ['conference', 'attendee', 'question', ]
