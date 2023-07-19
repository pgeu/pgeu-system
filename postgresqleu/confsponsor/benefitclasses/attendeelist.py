from django import forms
from django.core.exceptions import ValidationError
from postgresqleu.confsponsor.backendforms import BackendSponsorshipLevelBenefitForm

import base64
import io as StringIO
import csv

from .base import BaseBenefit, BaseBenefitForm

from postgresqleu.confreg.models import ConferenceRegistration
from postgresqleu.util.time import today_conference


class AttendeeListForm(BaseBenefitForm):
    confirm = forms.ChoiceField(label="Claim benefit", choices=((0, '* Choose'), (1, 'Claim this benefit'), (2, 'Decline this benefit')))

    def clean_confirm(self):
        if not int(self.cleaned_data['confirm']) in (1, 2):
            raise ValidationError('You must decide if you want to claim this benefit')
        return self.cleaned_data['confirm']


class AttendeeList(BaseBenefit):
    @classmethod
    def get_backend_form(self):
        return BackendSponsorshipLevelBenefitForm

    def generate_form(self):
        return AttendeeListForm

    def save_form(self, form, claim, request):
        if int(form.cleaned_data['confirm']) == 2:
            return False
        return True

    def render_claimdata(self, claimedbenefit, isadmin):
        if claimedbenefit.declined:
            return ""
        if claimedbenefit.confirmed:
            if self.level.conference.enddate < today_conference():
                data = StringIO.StringIO()
                c = csv.writer(data, delimiter=';')
                for r in ConferenceRegistration.objects.filter(conference=self.level.conference,
                                                               payconfirmedat__isnull=False,
                                                               canceledat__isnull=True,
                                                               shareemail=True).order_by('lastname', 'firstname'):
                    c.writerow([r.lastname,
                                r.firstname,
                                r.email,
                                r.company,
                                r.country])

                ret = StringIO.StringIO()
                ret.write("<p>This benefit lets you download a list of users who have explicitly opted in to having their information shared. You can download the list by clicking <a href=\"data:text/plain;charset=utf8;base64,")
                ret.write(base64.b64encode(data.getvalue().encode('utf8')).decode('utf8'))
                ret.write("\">here</a>. Please be careful with how you handle this personal data!</p>")
                return ret.getvalue()
            else:
                return "List of attendees will be made available here once the conference is over."
        else:
            return ""
