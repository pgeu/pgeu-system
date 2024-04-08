from django import forms


class BaseBenefit(object):
    can_autoconfirm = True
    can_multiclaim = True

    def __init__(self, level, params):
        self.level = level
        self.params = params

    def render_claimdata(self, claimedbenefit, isadmin):
        return ''

    def render_reportinfo(self, claimedbenefit):
        return ''

    def can_unclaim(self, claimedbenefit):
        return True

    def save_form(self, form, claim, request):
        # Return:
        # True -> proceed normally
        # False -> benefit declined
        raise Exception("Form saving not implemented!")

    def process_confirm(self, claim):
        # Return:
        # True -> send the "benefit confirmed" for non-auto benefits
        # False -> don't send it
        return True

    def process_unclaim(self, claim):
        pass

    def validate_parameters(self):
        pass

    def transform_parameters(self, oldconference, newconference):
        pass

    def inject_summary_section(self, claimedbenefit):
        return None


class BaseBenefitForm(forms.Form):
    def __init__(self, benefit, sponsor, *args, **kwargs):
        self.params = benefit.class_parameters
        self.sponsor = sponsor
        super(BaseBenefitForm, self).__init__(*args, **kwargs)
