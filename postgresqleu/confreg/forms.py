from django import forms
from django.forms.fields import *

from postgresqleu.confreg.models import *

class ConferenceRegistrationForm(forms.ModelForm):
	def clean_regtype(self):
		newval = self.cleaned_data.get('regtype')
		if newval and not newval.active:
			raise forms.ValidationError('Registration type "%s" is currently not available.' % newval)
		if self.instance and self.instance.payconfirmedat:
			if newval != self.instance.regtype:
				raise forms.ValidationError('You cannot change type of registration once your payment has been confirmed!')

		return newval

	class Meta:
		model = ConferenceRegistration
		exclude = ('conference','attendee','payconfirmedat','payconfirmedby',)
