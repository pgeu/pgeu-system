from django import forms
from django.core.validators import MaxValueValidator

import base64
import os
import simplejson
import cStringIO as StringIO

from base import BaseBenefit

from postgresqleu.confreg.models import RegistrationType, PrepaidBatch, PrepaidVoucher

def _validate_params(level, params):
	try:
		j = simplejson.loads(params)
		if sorted(j.keys()) != [u"num", u"type"]:
			raise Exception("Parameters 'num' and 'type' are mandatory")
		if int(j['num']) < 1:
			raise Exception("Parameter 'num' must be positive integer!")
		if not RegistrationType.objects.filter(conference=level.conference, regtype=j['type']).exists():
			raise Exception("Registation type '%s' does not exist" % j['type'])
		return j
	except simplejson.JSONDecodeError:
		raise Exception("Can't parse JSON")


class EntryVouchersForm(forms.Form):
	vouchercount = forms.IntegerField(label='Number of vouchers', min_value=0)

	def __init__(self, benefit, *args, **kwargs):
		self.params = _validate_params(benefit.level, benefit.class_parameters)

		super(EntryVouchersForm, self).__init__(*args, **kwargs)

		self.fields['vouchercount'].validators.append(MaxValueValidator(int(self.params['num'])))
		self.fields['vouchercount'].help_text = "Enter the number of vouchers to generate (up to %s). Please note that you cannot generate more vouchers at a later date, so please generate all the ones you want at once. If you do not want any sponsor vouchers, we ask you to please claim the number 0, so we have it for our records." % int(self.params['num'])

class EntryVouchers(BaseBenefit):
	description = "Claim entry vouchers"
	default_params = '{}'
	def validate_params(self):
		try:
			_validate_params(self.level, self.params)
		except Exception, e:
			return e


	def generate_form(self):
		return EntryVouchersForm

	def save_form(self, form, claim, request):
		j = _validate_params(self.level, self.params)
		if int(form.cleaned_data['vouchercount']) == 0:
			# No vouchers --> unclaim this benefit
			claim.claimdata = "0"
			claim.declined = True
			claim.confirmed = True
		else:
			# Actual number, form has been validated, so create the vouchers.
			batch = PrepaidBatch(conference=self.level.conference,
								 regtype=RegistrationType.objects.get(conference=self.level.conference, regtype=j['type']),
								 buyer=request.user,
								 buyername="%s %s" % (request.user.first_name, request.user.last_name))
			batch.save()
			for n in range(0, int(form.cleaned_data['vouchercount'])):
				v = PrepaidVoucher(conference=self.level.conference,
								   vouchervalue=base64.b64encode(os.urandom(37)).rstrip('='),
								   batch=batch)
				v.save()

			claim.claimdata = batch.id
			claim.confirmed = True # Always confirmed, they're generated after all
		return True

	def render_claimdata(self, claimedbenefit):
		# Look up our batch
		batch = PrepaidBatch.objects.get(pk=int(claimedbenefit.claimdata))
		vouchers = list(batch.prepaidvoucher_set.all())

		generated = len(vouchers)
		used = len([1 for v in vouchers if v.usedate])

		s = StringIO.StringIO()
		s.write("<p>%s vouchers were generated, %s have been used.</p>" % (generated, used))
		s.write("<table><tr><th>Voucher code</th><th>Used by</th><th>Used at</th></tr>")
		for v in vouchers:
			s.write("<tr><td><code>{0}</code></td><td>{1}</td><td>{2}</td></tr>".format(v.vouchervalue, v.user and v.user.fullname.encode('utf8'), v.usedate and v.usedate or ''))
		s.write("</table>")
		return s.getvalue()
