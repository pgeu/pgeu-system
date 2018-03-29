import django.forms
import django.forms.widgets
from django.forms.widgets import TextInput


from selectable.forms.widgets import AutoCompleteSelectWidget, AutoCompleteSelectMultipleWidget

from postgresqleu.util.admin import SelectableWidgetAdminFormMixin
from postgresqleu.util.forms import ConcurrentProtectedModelForm

from postgresqleu.accountinfo.lookups import UserLookup
from postgresqleu.confreg.lookups import RegistrationLookup

from postgresqleu.confreg.models import Conference, ConferenceRegistration, ConferenceAdditionalOption
from postgresqleu.confreg.models import RegistrationClass, RegistrationType, RegistrationDay

class BackendDateInput(TextInput):
	def __init__(self, *args, **kwargs):
		kwargs.update({'attrs': {'type': 'date', 'required-pattern': '[0-9]{4}-[0-9]{2}-[0-9]{2}'}})
		super(BackendDateInput, self).__init__(*args, **kwargs)

class BackendForm(ConcurrentProtectedModelForm):
	selectize_multiple_fields = None
	vat_fields = {}
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


class BackendRegistrationDayForm(BackendForm):
	list_fields = [ 'day', ]
	class Meta:
		model = RegistrationDay
		fields = ['day', ]
