from django import forms
from django.forms.fields import *

from postgresqleu.confreg.models import *

class ConferenceRegistrationForm(forms.ModelForm):
	def clean_regtype(self):
		if self.instance and self.instance.payconfirmedat:
			if self.cleaned_data.get('regtype') != self.instance.regtype:
				raise forms.ValidationError('You cannot change type of registration once your payment has been confirmed!')

		return self.cleaned_data.get('regtype')

	class Meta:
		model = ConferenceRegistration
		exclude = ('conference','attendee','payconfirmedat','payconfirmedby',)
