from django import forms

from confreg.models import RegistrationType, ConferenceRegistration
from models import Wikipage

class WikipageEditForm(forms.ModelForm):
	class Meta:
		model = Wikipage
		fields = ('contents',)

class WikipageAdminEditForm(forms.ModelForm):
	def __init__(self, *args, **kwargs):
		super(WikipageAdminEditForm, self).__init__(*args, **kwargs)
		self.fields['author'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
		self.fields['author'].label_from_instance = lambda r: "{0} <{1}>".format(r.fullname, r.email)
		self.fields['viewer_regtype'].queryset = RegistrationType.objects.filter(conference=self.instance.conference)
		self.fields['editor_regtype'].queryset = RegistrationType.objects.filter(conference=self.instance.conference)
		self.fields['viewer_attendee'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
		self.fields['viewer_attendee'].label_from_instance = lambda r: "{0} <{1}>".format(r.fullname, r.email)
		self.fields['editor_attendee'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
		self.fields['editor_attendee'].label_from_instance = lambda r: "{0} <{1}>".format(r.fullname, r.email)

	class Meta:
		model = Wikipage
		exclude = ['conference', ]

