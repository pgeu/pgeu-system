from django import forms

from postgresqleu.util.validators import validate_json_structure

class BaseBenefit(object):
    default_params = {}
    def __init__(self, level, params):
        self.level = level
        self.params = params

    def do_validate_params(self):
        validate_json_structure(self.params, self.param_struct)
        self.validate_params()

    def validate_params(self):
        pass

    def render_claimdata(self, claimedbenefit):
        return ''

    def save_form(self, form, claim, request):
        raise Exception("Form saving not implemented!")

class BaseBenefitForm(forms.Form):
    def __init__(self, benefit, *args, **kwargs):
        self.params = benefit.class_parameters
        super(BaseBenefitForm, self).__init__(*args, **kwargs)
