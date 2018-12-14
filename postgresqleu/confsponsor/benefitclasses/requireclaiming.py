from django import forms
from django.core.exceptions import ValidationError

from base import BaseBenefit, BaseBenefitForm

class RequireClaimingForm(BaseBenefitForm):
    confirm = forms.ChoiceField(label="Claim benefit", choices=((0, '* Choose'), (1, 'Claim this benefit'), (2, 'Decline this benefit')))

    def clean_confirm(self):
        if not int(self.cleaned_data['confirm']) in (1,2):
            raise ValidationError('You must decide if you want to claim this benefit')
        return self.cleaned_data['confirm']

class RequireClaiming(BaseBenefit):
    description = "Requires explicit claiming"
    param_struct = {}

    def generate_form(self):
        return RequireClaimingForm

    def save_form(self, form, claim, request):
        if int(form.cleaned_data['confirm']) == 2:
            # This is actually a deny
            claim.declined = True
            claim.confirmed = True
            return True

        return True
