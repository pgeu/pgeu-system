from django import forms
from django.core.exceptions import ValidationError
from django.conf import settings

from models import Member

class MemberForm(forms.ModelForm):
	class Meta:
		model = Member
		exclude = ('user', 'paiduntil', 'membersince', 'activeinvoice', 'expiry_warning_sent', 'country_exception')

	def clean_country(self):
		if self.instance.country_exception:
			# No country checking for this member
			return self.cleaned_data['country']

		if settings.MEMBERSHIP_COUNTRY_VALIDATOR:
			msg = settings.MEMBERSHIP_COUNTRY_VALIDATOR(self.cleaned_data['country'])
			if isinstance(msg, str):
				raise ValidationError(msg)
		return self.cleaned_data['country']
