from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Q
import django.forms
import django.forms.widgets
from django.forms.widgets import TextInput

import datetime

from selectable.forms.widgets import AutoCompleteSelectWidget, AutoCompleteSelectMultipleWidget

from postgresqleu.util.admin import SelectableWidgetAdminFormMixin
from postgresqleu.util.forms import ConcurrentProtectedModelForm

from postgresqleu.accountinfo.lookups import UserLookup
from postgresqleu.confreg.lookups import RegistrationLookup

from postgresqleu.confreg.models import Conference, ConferenceRegistration, ConferenceAdditionalOption
from postgresqleu.confreg.models import RegistrationClass, RegistrationType, RegistrationDay
from postgresqleu.confreg.models import ConferenceSession, Track, Room
from postgresqleu.confreg.models import ConferenceSessionScheduleSlot, VolunteerSlot

from postgresqleu.confreg.models import valid_status_transitions, get_status_string

class BackendDateInput(TextInput):
	def __init__(self, *args, **kwargs):
		kwargs.update({'attrs': {'type': 'date', 'required-pattern': '[0-9]{4}-[0-9]{2}-[0-9]{2}'}})
		super(BackendDateInput, self).__init__(*args, **kwargs)

class BackendForm(ConcurrentProtectedModelForm):
	selectize_multiple_fields = None
	vat_fields = {}
	verbose_field_names = {}
	def __init__(self, conference, *args, **kwargs):
		self.conference = conference
		super(BackendForm, self).__init__(*args, **kwargs)
		self.fix_fields()

		# Adjust widgets
		for k,v in self.fields.items():
			if isinstance(v, django.forms.fields.DateField):
				v.widget = BackendDateInput()

		for field, vattype in self.vat_fields.items():
			self.fields[field].widget.attrs['class'] = 'backend-vat-field backend-vat-{0}-field'.format(vattype)

	def fix_fields(self):
		pass

	@classmethod
	def get_field_verbose_name(self, f):
		if f in self.verbose_field_names:
			return self.verbose_field_names[f]
		return self.Meta.model._meta.get_field(f).verbose_name.capitalize()

class BackendConferenceForm(BackendForm):
	class Meta:
		model = Conference
		fields = ['active', 'callforpapersopen', 'callforsponsorsopen', 'feedbackopen',
				  'conferencefeedbackopen', 'scheduleactive', 'sessionsactive',
				  'schedulewidth', 'pixelsperminute',
				  'testers', 'talkvoters', 'staff', 'volunteers',
				  'asktshirt', 'askfood', 'askshareemail', 'skill_levels',
				  'additionalintro', 'callforpapersintro', 'sendwelcomemail', 'welcomemail',
				  'invoice_autocancel_hours', 'attendees_before_waitlist']
	selectize_multiple_fields = ['testers', 'talkvoters', 'staff', 'volunteers']


	def fix_fields(self):
		self.fields['testers'].label_from_instance = lambda x: u'{0} {1} ({2})'.format(x.first_name, x.last_name, x.username)
		self.fields['talkvoters'].label_from_instance = lambda x: u'{0} {1} ({2})'.format(x.first_name, x.last_name, x.username)
		self.fields['staff'].label_from_instance = lambda x: u'{0} {1} ({2})'.format(x.first_name, x.last_name, x.username)
		self.fields['volunteers'].label_from_instance = lambda x: u'{0} <{1}>'.format(x.fullname, x.email)
		self.fields['volunteers'].queryset = ConferenceRegistration.objects.filter(conference=self.conference)


class BackendRegistrationForm(BackendForm):
	class Meta:
		model = ConferenceRegistration
		fields = ['firstname', 'lastname', 'company', 'address', 'country', 'phone', 'shirtsize', 'dietary', 'twittername', 'nick', 'shareemail']

	def fix_fields(self):
		if not self.conference.askfood:
			del self.fields['dietary']
		if not self.conference.asktshirt:
			del self.fields['shirtsize']
		if not self.conference.askshareemail:
			del self.fields['shareemail']
		self.update_protected_fields()

class BackendRegistrationClassForm(BackendForm):
	list_fields = ['regclass', 'badgecolor', 'badgeforegroundcolor']
	class Meta:
		model = RegistrationClass
		fields = ['regclass', 'badgecolor', 'badgeforegroundcolor']

class BackendRegistrationTypeForm(BackendForm):
	list_fields = ['regtype', 'regclass', 'cost', 'active', 'sortkey']
	vat_fields = {'cost': 'reg'}
	class Meta:
		model = RegistrationType
		fields = ['regtype', 'regclass', 'cost', 'active', 'activeuntil', 'days', 'sortkey', 'specialtype', 'alertmessage', 'invoice_autocancel_hours', 'requires_option', 'upsell_target']

	def fix_fields(self):
		self.fields['regclass'].queryset = RegistrationClass.objects.filter(conference=self.conference)
		self.fields['requires_option'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.conference)
		if RegistrationDay.objects.filter(conference=self.conference).exists():
			self.fields['days'].queryset = RegistrationDay.objects.filter(conference=self.conference)
		else:
			del self.fields['days']
			self.update_protected_fields()

		if not ConferenceAdditionalOption.objects.filter(conference=self.conference).exists():
			del self.fields['requires_option']
			del self.fields['upsell_target']
			self.update_protected_fields()

	def clean_cost(self):
		if self.instance and self.instance.cost != self.cleaned_data['cost']:
			if self.instance.conferenceregistration_set.filter(Q(payconfirmedat__isnull=False)|Q(invoice__isnull=False)|Q(bulkpayment__isnull=False)).exists():
				raise ValidationError("This registration type has been used, so the cost can no longer be changed")

		return self.cleaned_data['cost']

class BackendRegistrationDayForm(BackendForm):
	list_fields = [ 'day', ]
	class Meta:
		model = RegistrationDay
		fields = ['day', ]

class BackendTrackForm(BackendForm):
	list_fields = ['trackname', 'sortkey']
	class Meta:
		model = Track
		fields = ['trackname', 'sortkey', 'color', 'incfp']

class BackendRoomForm(BackendForm):
	list_fields = ['roomname', 'sortkey']
	class Meta:
		model = Room
		fields = ['roomname', 'sortkey']

class BackendConferenceSessionForm(BackendForm):
	list_fields = [ 'title', 'speaker_list', 'status_string', 'starttime', 'track', 'room']
	verbose_field_names = {
		'speaker_list': 'Speakers',
		'status_string': 'Status',
	}
	selectize_multiple_fields = ['speaker']

	class Meta:
		model = ConferenceSession
		fields = ['title', 'speaker', 'status', 'starttime', 'endtime', 'cross_schedule',
				  'track', 'room', 'can_feedback', 'skill_level', 'abstract', 'submissionnote']

	def fix_fields(self):
		self.fields['track'].queryset = Track.objects.filter(conference=self.conference)
		self.fields['room'].queryset = Room.objects.filter(conference=self.conference)

		self.fields['starttime'].validators.extend([
			MinValueValidator(datetime.datetime.combine(self.conference.startdate, datetime.time(0,0,0))),
			MaxValueValidator(datetime.datetime.combine(self.conference.enddate+datetime.timedelta(days=1), datetime.time(0,0,0))),
		])
		self.fields['endtime'].validators.extend([
			MinValueValidator(datetime.datetime.combine(self.conference.startdate, datetime.time(0,0,0))),
			MaxValueValidator(datetime.datetime.combine(self.conference.enddate+datetime.timedelta(days=1), datetime.time(0,0,0))),
		])

		if self.instance.status != self.instance.lastnotifiedstatus:
			self.fields['status'].help_text = '<b>Warning!</b> This session has <a href="/events/admin/{0}/sessionnotifyqueue/">pending notifications</a> that have not been sent. You probably want to make sure those are sent before editing the status!'.format(self.conference.urlname)

		if not self.conference.skill_levels:
			del self.fields['skill_level']
			self.update_protected_fields()

	def clean(self):
		cleaned_data = super(BackendConferenceSessionForm, self).clean()

		if cleaned_data.get('starttime') and not cleaned_data.get('endtime'):
			self.add_error('endtime', 'End time must be specified if start time is!')
		elif cleaned_data.get('endtime') and not cleaned_data.get('starttime'):
			self.add_error('starttime', 'Start time must be specified if end time is!')
		elif cleaned_data.get('starttime') and cleaned_data.get('endtime'):
			if cleaned_data.get('endtime') < cleaned_data.get('starttime'):
				self.add_error('endtime', 'End time must be later than start time!')

		if cleaned_data.get('cross_schedule') and cleaned_data.get('room'):
			self.add_error('room', 'Room cannot be specified for cross schedule sessions!')

		return cleaned_data

	def clean_status(self):
		newstatus = self.cleaned_data.get('status')
		if newstatus == self.instance.status:
			return newstatus

		# If there are speakers on the session, we lock it to the workflow. For sessions
		# with no speakers, anything goes
		if not self.cleaned_data.get('speaker').exists():
			return newstatus

		if not newstatus in valid_status_transitions[self.instance.status]:
			raise ValidationError("Sessions with speaker cannot change from {0} to {1}. Only one of {2} is allowed.".format(
				get_status_string(self.instance.status),
				get_status_string(newstatus),
				", ".join(["{0} ({1})".format(get_status_string(s), v) for s,v in valid_status_transitions[self.instance.status].items()]),
			))

		return newstatus

class BackendConferenceSessionSlotForm(BackendForm):
	list_fields = [ 'starttime', 'endtime', ]

	class Meta:
		model = ConferenceSessionScheduleSlot
		fields = ['starttime', 'endtime' ]

class BackendVolunteerSlotForm(BackendForm):
	list_fields = [ 'timerange', 'title', 'min_staff', 'max_staff' ]

	class Meta:
		model = VolunteerSlot
		fields = [ 'timerange', 'title', 'min_staff', 'max_staff' ]

	def clean(self):
		cleaned_data = super(BackendVolunteerSlotForm, self).clean()
		if cleaned_data.get('min_staff') > cleaned_data.get('max_staff'):
			self.add_error('max_staff', 'Max staff must be at least as high as min_staff!')

		return cleaned_data
