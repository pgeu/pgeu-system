from django import forms
from django.core.validators import MaxValueValidator

import base64
import os
import cStringIO as StringIO

from base import BaseBenefit, BaseBenefitForm

from postgresqleu.mailqueue.util import send_template_mail

from postgresqleu.confreg.models import RegistrationType, PrepaidBatch, PrepaidVoucher


class EntryVouchersForm(BaseBenefitForm):
    vouchercount = forms.IntegerField(label='Number of vouchers', min_value=0)

    def __init__(self, *args, **kwargs):
        super(EntryVouchersForm, self).__init__(*args, **kwargs)

        self.fields['vouchercount'].validators.append(MaxValueValidator(int(self.params['num'])))
        self.fields['vouchercount'].help_text = "Enter the number of vouchers to generate (up to %s). Please note that you cannot generate more vouchers at a later date, so please generate all the ones you want at once. If you do not want any sponsor vouchers, we ask you to please claim the number 0, so we have it for our records." % int(self.params['num'])


class EntryVouchers(BaseBenefit):
    description = "Claim entry vouchers"
    default_params = {"num": 1, "type": ""}
    param_struct = {
        'num': int,
        'type': unicode,
    }

    def validate_params(self):
        if not RegistrationType.objects.filter(conference=self.level.conference, regtype=self.params['type']).exists():
            raise forms.ValidationError("Registration type '%s' does not exist" % self.params['type'])

    def generate_form(self):
        return EntryVouchersForm

    def save_form(self, form, claim, request):
        if int(form.cleaned_data['vouchercount']) == 0:
            # No vouchers --> unclaim this benefit
            claim.claimdata = "0"
            claim.declined = True
            claim.confirmed = True
        else:
            # Actual number, form has been validated, so create the vouchers.
            batch = PrepaidBatch(conference=self.level.conference,
                                 regtype=RegistrationType.objects.get(conference=self.level.conference, regtype=self.params['type']),
                                 buyer=request.user,
                                 buyername="%s %s" % (request.user.first_name, request.user.last_name),
                                 sponsor=claim.sponsor)
            batch.save()
            vouchers = []
            for n in range(0, int(form.cleaned_data['vouchercount'])):
                v = PrepaidVoucher(conference=self.level.conference,
                                   vouchervalue=base64.b64encode(os.urandom(37)).rstrip('='),
                                   batch=batch)
                v.save()
                vouchers.append(v)

            # Send an email about the new vouchers
            send_template_mail(self.level.conference.sponsoraddr,
                               request.user.email,
                               "Entry vouchers for {0}".format(self.level.conference),
                               'confreg/mail/prepaid_vouchers.txt',
                               {
                                   'batch': batch,
                                   'vouchers': vouchers,
                                   'conference': self.level.conference,
                               }
                           )

            # Finally, finish the claim
            claim.claimdata = batch.id
            claim.confirmed = True  # Always confirmed, they're generated after all
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
            s.write("<tr><td><code>{0}</code></td><td>{1}</td><td>{2}</td></tr>".format(v.vouchervalue, v.user and v.user.fullname.encode('utf8') or '', v.usedate and v.usedate or ''))
        s.write("</table>")
        return s.getvalue()
