from django import forms
from django.forms import RadioSelect
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

rating_choices = (
    (1, '1'),
    (2, '2'),
    (3, '3'),
    (4, '4'),
    (5, '5'),
    (0, 'N/A'),
)

class ConferenceSessionFeedbackForm(forms.ModelForm):
	topic_importance = forms.ChoiceField(widget=RadioSelect,choices=rating_choices, label='Importance of the topic')
	content_quality = forms.ChoiceField(widget=RadioSelect,choices=rating_choices, label='Quality of the content')
	speaker_knowledge = forms.ChoiceField(widget=RadioSelect,choices=rating_choices, label='Speakers knowledge of the subject')
	speaker_quality = forms.ChoiceField(widget=RadioSelect,choices=rating_choices, label='Speakers presentation skills')

	class Meta:
		model = ConferenceSessionFeedback
		exclude = ('conference','attendee','session')

