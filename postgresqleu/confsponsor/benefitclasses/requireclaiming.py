from django import forms
from django.core.exceptions import ValidationError
from postgresqleu.confsponsor.backendforms import BackendSponsorshipLevelBenefitForm

from .base import BaseBenefit, BaseBenefitForm


class RequireClaimingForm(BaseBenefitForm):
    confirm = forms.ChoiceField(label="Claim benefit", choices=((0, '* Choose'), (1, 'Claim this benefit'), (2, 'Decline this benefit')))

    def clean_confirm(self):
        if not int(self.cleaned_data['confirm']) in (1, 2):
            raise ValidationError('You must decide if you want to claim this benefit')
        return self.cleaned_data['confirm']


class RequireClaimingBackendForm(BackendSponsorshipLevelBenefitForm):
    autoconfirm = forms.BooleanField(label="Automatically confirm", required=False,
                                     help_text="Automatically confirm this benefit when it's claimed")

    class_param_fields = ['autoconfirm', ]


class RequireClaiming(BaseBenefit):
    @classmethod
    def get_backend_form(self):
        return RequireClaimingBackendForm

    def generate_form(self):
        return RequireClaimingForm

    def save_form(self, form, claim, request):
        if int(form.cleaned_data['confirm']) == 2:
            # This is actually a deny
            claim.declined = True
            claim.confirmed = True
            return True
        else:
            # It's a claim! Should it be auto-confirmed automatically, or require an admin?
            if self.params.get('autoconfirm', False):
                claim.confirmed = True
            return True
