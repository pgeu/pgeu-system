from django import forms
from django.core.exceptions import ValidationError
from django.conf import settings

from .models import Member, get_config
from .util import validate_country


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        fields = ('fullname', 'country', 'listed')

    def clean_country(self):
        if self.instance.country_exception:
            # No country checking for this member
            return self.cleaned_data['country']

        validate_country(get_config().country_validator, self.cleaned_data['country'])

        return self.cleaned_data['country']


class ProxyVoterForm(forms.Form):
    name = forms.CharField(min_length=5, max_length=100, help_text="Name of proxy voter. Leave empty to cancel proxy voting.", required=False)
