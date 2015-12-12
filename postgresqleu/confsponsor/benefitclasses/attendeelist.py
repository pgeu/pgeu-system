from django import forms
from django.core.exceptions import ValidationError

from datetime import datetime
import base64
import cStringIO as StringIO
import csv
import json

from base import BaseBenefit

from postgresqleu.confreg.models import ConferenceRegistration

class AttendeeListForm(forms.Form):
	confirm = forms.ChoiceField(label="Claim benefit", choices=((0, '* Choose'), (1, 'Claim this benefit'), (2, 'Decline this benefit')))

	def __init__(self, benefit, *args, **kwargs):
		super(AttendeeListForm, self).__init__(*args, **kwargs)

		if benefit.class_parameters:
			params = json.loads(benefit.class_parameters)
			if params.has_key('claimcheckbox'):
				self.fields['confirm'].help_text = params['claimcheckbox']

	def clean_confirm(self):
		if not int(self.cleaned_data['confirm']) in (1,2):
			raise ValidationError('You must decide if you want to claim this benefit')
		return self.cleaned_data['confirm']

class AttendeeList(BaseBenefit):
	description = "List of attendee email addresses"

	def validate_params(self):
		# Just see that it's valid json, and then pass it upwards
		try:
			json.loads(self.params)
		except Exception, e:
			return e

	def generate_form(self):
		return AttendeeListForm

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

	def render_claimdata(self, claimedbenefit):
		if claimedbenefit.declined:
			return ""
		if claimedbenefit.confirmed:
			if self.level.conference.enddate < datetime.today().date():
				data = StringIO.StringIO()
				c=csv.writer(data, delimiter=';')
				for r in ConferenceRegistration.objects.filter(conference=self.level.conference,
															   payconfirmedat__isnull=False,
															   shareemail=True).order_by('lastname', 'firstname'):
					c.writerow([r.lastname.encode('utf8'),
								r.firstname.encode('utf8'),
								r.email.encode('utf8'),
								r.company.encode('utf8'),
								r.country.name.encode('utf8')])

				ret = StringIO.StringIO()
				ret.write("<p>This benefit lets you download a list of users who have explicitly opted in to having their information shared. You can download the list by clicking <a href=\"data:text/plain;charset=utf8;base64,")
				ret.write(base64.b64encode(data.getvalue()))
				ret.write("\">here</a>. Please be careful with how you handle this personal data!</p>")
				return ret.getvalue()
			else:
				return "List of attendees will be made available here once the conference is over."
		else:
			return ""

