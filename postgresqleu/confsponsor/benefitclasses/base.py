from django import forms

from postgresqleu.util.validators import validate_json_structure


class BaseBenefit(object):
    def __init__(self, level, params):
        self.level = level
        self.params = params

    def render_claimdata(self, claimedbenefit):
        return ''

    def can_unclaim(self, claimedbenefit):
        return True

    def save_form(self, form, claim, request):
        raise Exception("Form saving not implemented!")


class BaseBenefitForm(forms.Form):
    def __init__(self, benefit, *args, **kwargs):
        self.params = benefit.class_parameters
        super(BaseBenefitForm, self).__init__(*args, **kwargs)
