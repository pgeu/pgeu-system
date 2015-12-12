from django import forms
from django.core.exceptions import ValidationError

import json

from base import BaseBenefit

class RequireClaimingForm(forms.Form):
	confirm = forms.ChoiceField(label="Claim benefit", choices=((0, '* Choose'), (1, 'Claim this benefit'), (2, 'Decline this benefit')))

	def __init__(self, benefit, *args, **kwargs):
		super(RequireClaimingForm, self).__init__(*args, **kwargs)

		if benefit.class_parameters:
			params = json.loads(benefit.class_parameters)
			if params.has_key('claimcheckbox'):
				self.fields['confirm'].help_text = params['claimcheckbox']

	def clean_confirm(self):
		if not int(self.cleaned_data['confirm']) in (1,2):
			raise ValidationError('You must decide if you want to claim this benefit')
		return self.cleaned_data['confirm']

class RequireClaiming(BaseBenefit):
	description = "Requires explicit claiming"

	def validate_params(self):
		# Just see that it's valid json, and then pass it upwards
		try:
			json.loads(self.params)
		except Exception, e:
			return e

	def generate_form(self):
		return RequireClaimingForm

	def save_form(self, form, claim, request):
		try:
			p = json.loads(self.params)
		except Exception:
			p = {}

		if int(form.cleaned_data['confirm']) == 2:
			# This is actually a deny
			claim.declined = True
			claim.confirmed = True
			return True

		if p.has_key('autoconfirm') and p['autoconfirm']:
			claim.confirmed = True
			return False
		return True
