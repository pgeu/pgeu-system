from django import forms
from django.forms import ValidationError

from models import Sponsor, SponsorMail, SponsorshipLevel
from confreg.models import Conference

class SponsorSignupForm(forms.Form):
	name = forms.CharField(label="Company name *", min_length=3, max_length=100)
	address = forms.CharField(label="Company address *", min_length=10, max_length=500, widget=forms.Textarea)
	confirm = forms.BooleanField(help_text="Check this box to that you have read and agree to the terms in the contract")

	def __init__(self, conference, *args, **kwargs):
		self.conference = conference
		return super(SponsorSignupForm, self).__init__(*args, **kwargs)

	def clean_name(self):
		if Sponsor.objects.filter(conference=self.conference, name__iexact=self.cleaned_data['name']).exists():
			raise ValidationError("A sponsor with this name is already signed up for this conference!")
		return self.cleaned_data['name']


class SponsorSendEmailForm(forms.ModelForm):
	confirm = forms.BooleanField(label="Confirm", required=False)
	class Meta:
		model = SponsorMail
		exclude = ('conference', )

	def __init__(self, conference, *args, **kwargs):
		self.conference = conference
		super(SponsorSendEmailForm, self).__init__(*args, **kwargs)
		self.fields['levels'].widget = forms.CheckboxSelectMultiple()
		self.fields['levels'].queryset = SponsorshipLevel.objects.filter(conference=self.conference)

		if not (self.data.get('levels') and self.data.get('subject') and self.data.get('message')):
				del self.fields['confirm']

	def clean_confirm(self):
		if not self.cleaned_data['confirm']:
			raise ValidationError("Please check this box to confirm that you are really sending this email! There is no going back!")

class AdminCopySponsorshipLevelForm(forms.Form):
	targetconference = forms.ModelChoiceField(queryset=Conference.objects.all(), label='Target conference')
