from django.core.exceptions import ValidationError
from django import forms

import simplejson

from base import BaseBenefit

def _validate_params(params):
	try:
		j = simplejson.loads(params)
		for k in j.keys():
			if not k in [u"minwords", u"maxwords", u"minchars", u"maxchars"]:
				raise Exception("Parameter '%s' is unknown" % k)
		return j
	except simplejson.JSONDecodeError:
		raise Exception("Can't parse JSON")


class ProvideTextForm(forms.Form):
	decline = forms.BooleanField(label='Decline this benefit', required=False)
	text = forms.CharField(label='Text', required=False, widget=forms.Textarea)

	def __init__(self, benefit, *args, **kwargs):
		self.params = _validate_params(benefit.class_parameters)

		super(ProvideTextForm, self).__init__(*args, **kwargs)

	def clean(self):
		declined = self.cleaned_data.get('decline', False)
		if not declined:
			# If not declined, we will require the text
			if not self.cleaned_data.get('text', None):
				if not self._errors.has_key('text'):
					self._errors['text'] = self.error_class(['This field is required'])
		return self.cleaned_data

	def clean_text(self):
		if not self.cleaned_data.get('text', None):
			# This check is done int he global clean as well, so we accept it here in case it was
			# declined.
			return None

		d = self.cleaned_data['text']
		words = len(d.split())
		if self.params.has_key('minchars') and len(d) < self.params['minchars']:
			raise ValidationError('Must be at least %s characters.' % self.params['minchars'])
		if self.params.has_key('maxchars') and len(d) > self.params['maxchars']:
			raise ValidationError('Must be less than %s characters.' % self.params['maxchars'])
		if self.params.has_key('minwords') and words < self.params['minwords']:
			raise ValidationError('Must be at least %s words.' % self.params['minwords'])
		if self.params.has_key('maxwords') and words > self.params['maxwords']:
			raise ValidationError('Must be less than %s words.' % self.params['maxwords'])
		return d

class ProvideText(BaseBenefit):
	description = "Provide text string"
	default_params = '{}'
	def validate_params(self):
		try:
			_validate_params(self.params)
		except Exception, e:
			return e

	def generate_form(self):
		return ProvideTextForm

	def save_form(self, form, claim, request):
		if form.cleaned_data['decline']:
			claim.declined = True
			claim.confirmed = True
			return True

		claim.claimdata = form.cleaned_data['text']
		return True

	def render_claimdata(self, claimedbenefit):
		return claimedbenefit.claimdata
