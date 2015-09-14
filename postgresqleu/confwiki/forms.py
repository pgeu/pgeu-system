from django import forms
from django.core.exceptions import ValidationError

from confreg.models import RegistrationType, ConferenceRegistration
from models import Wikipage, Signup

class WikipageEditForm(forms.ModelForm):
	class Meta:
		model = Wikipage
		fields = ('contents',)

class WikipageAdminEditForm(forms.ModelForm):
	def __init__(self, *args, **kwargs):
		super(WikipageAdminEditForm, self).__init__(*args, **kwargs)
		self.fields['author'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
		self.fields['author'].label_from_instance = lambda r: u"{0} <{1}>".format(r.fullname, r.email)
		self.fields['viewer_regtype'].queryset = RegistrationType.objects.filter(conference=self.instance.conference)
		self.fields['editor_regtype'].queryset = RegistrationType.objects.filter(conference=self.instance.conference)
		self.fields['viewer_attendee'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
		self.fields['viewer_attendee'].label_from_instance = lambda r: u"{0} <{1}>".format(r.fullname, r.email)
		self.fields['editor_attendee'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
		self.fields['editor_attendee'].label_from_instance = lambda r: u"{0} <{1}>".format(r.fullname, r.email)

	class Meta:
		model = Wikipage
		exclude = ['conference', ]


class SignupSubmitForm(forms.Form):
	choice = forms.ChoiceField(required=False, label='')

	def __init__(self, signup, attendee_signup, *args, **kwargs):
		self.signup = signup
		self.attendee_signup = attendee_signup
		super(SignupSubmitForm, self).__init__(*args, **kwargs)

		if signup.options:
			choices = signup.options.split(',')
			self.fields['choice'].choices = [(k,k) for k in choices]
			self.fields['choice'].choices.insert(0, ('', ''))
		else:
			# This one is boolean only
			self.fields['choice'].choices = (('', ''), ('yes','Yes'), ('', 'No'), )

		if attendee_signup:
			self.fields['choice'].initial = attendee_signup.choice

	def clean_choice(self):
		if self.cleaned_data.get('choice', '') and self.signup.maxsignups > 0:
			# Verify maximum uses.
			if self.attendee_signup:
				currnum = self.signup.attendeesignup_set.exclude(id=self.attendee_signup.id).count()
			else:
				currnum = self.signup.attendeesignup_set.count()
			if currnum >= self.signup.maxsignups:
				raise ValidationError("This signup is limited to {0} attendees.".format(self.signup.maxsignups))
		return self.cleaned_data['choice']

class SignupAdminEditForm(forms.ModelForm):
	def __init__(self, *args, **kwargs):
		super(SignupAdminEditForm, self).__init__(*args, **kwargs)
		self.fields['author'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
		self.fields['author'].label_from_instance = lambda r: u"{0} <{1}>".format(r.fullname, r.email)
		self.fields['regtypes'].queryset = RegistrationType.objects.filter(conference=self.instance.conference)
		self.fields['attendees'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
		self.fields['attendees'].label_from_instance = lambda r: u"{0} <{1}>".format(r.fullname, r.email)

	class Meta:
		model = Signup
		exclude = ['conference', ]

