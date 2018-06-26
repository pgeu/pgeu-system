from django.core.exceptions import ValidationError
from django import forms

from base import BaseBenefit, BaseBenefitForm

class ProvideTextForm(BaseBenefitForm):
	decline = forms.BooleanField(label='Decline this benefit', required=False)
	text = forms.CharField(label='Text', required=False, widget=forms.Textarea)

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
		if self.params.get('minchars', 0) and len(d) < self.params['minchars']:
			raise ValidationError('Must be at least %s characters.' % self.params['minchars'])
		if self.params.get('maxchars', 0) and len(d) > self.params['maxchars']:
			raise ValidationError('Must be less than %s characters.' % self.params['maxchars'])
		if self.params.get('minwords', 0) and words < self.params['minwords']:
			raise ValidationError('Must be at least %s words.' % self.params['minwords'])
		if self.params.get('maxwords', 0) and words > self.params['maxwords']:
			raise ValidationError('Must be less than %s words.' % self.params['maxwords'])
		return d

class ProvideText(BaseBenefit):
	description = "Provide text string"
	default_params = {"minwords": 0, "maxwords": 0, "minchars": 0, "maxchars": 0}
	param_struct = {
		'minwords': int,
		'maxwords': int,
		'minchars': int,
		'maxchars': int,
	}

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
