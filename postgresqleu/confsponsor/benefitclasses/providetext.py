from django.core.exceptions import ValidationError
from django import forms
from django.core.validators import MinValueValidator

from postgresqleu.confsponsor.backendforms import BackendSponsorshipLevelBenefitForm

from .base import BaseBenefit, BaseBenefitForm


class ProvideTextForm(BaseBenefitForm):
    decline = forms.BooleanField(label='Decline this benefit', required=False)
    text = forms.CharField(label='Text', required=False, widget=forms.Textarea)

    def clean(self):
        declined = self.cleaned_data.get('decline', False)
        if not declined:
            # If not declined, we will require the text
            if not self.cleaned_data.get('text', None):
                if 'text' not in self._errors:
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


class ProvideTextBackendForm(BackendSponsorshipLevelBenefitForm):
    minwords = forms.IntegerField(label="Minimum words", validators=[MinValueValidator(0)], initial=0)
    maxwords = forms.IntegerField(label="Maximum words", validators=[MinValueValidator(0)], initial=0)
    minchars = forms.IntegerField(label="Minimum characters", validators=[MinValueValidator(0)], initial=0)
    maxchars = forms.IntegerField(label="Maximum characters", validators=[MinValueValidator(0)], initial=0)

    class_param_fields = ['minwords', 'maxwords', 'minchars', 'maxchars']

    def clean(self):
        d = super(ProvideTextBackendForm, self).clean()
        if d.get('minwords', 0) and d.get('maxwords', 0):
            if d.get('minwords', 0) >= d.get('maxwords', 0):
                self.add_error('maxwords', 'Maximum words must be higher than minimum words')

        if d.get('minchars', 0) and d.get('maxchars', 0):
            if d.get('minchars', 0) >= d.get('maxchars', 0):
                self.add_error('maxchars', 'Maximum characters must be higher than minimum characters')

        return d


class ProvideText(BaseBenefit):
    @classmethod
    def get_backend_form(self):
        return ProvideTextBackendForm

    def generate_form(self):
        return ProvideTextForm

    def save_form(self, form, claim, request):
        if form.cleaned_data['decline']:
            claim.declined = True
            claim.confirmed = True
            return True

        claim.claimjson['text'] = form.cleaned_data['text']
        return True

    def render_claimdata(self, claimedbenefit, isadmin):
        return claimedbenefit.claimjson['text']

    def can_unclaim(self, claimedbenefit):
        return True
