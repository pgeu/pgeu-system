from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator, ValidationError

import base64
import os
import io as StringIO

from .base import BaseBenefit, BaseBenefitForm

from postgresqleu.confsponsor.backendforms import BackendSponsorshipLevelBenefitForm

from postgresqleu.confreg.models import RegistrationType, PrepaidBatch, PrepaidVoucher
from postgresqleu.confreg.util import send_conference_mail


class EntryVouchersForm(BaseBenefitForm):
    vouchercount = forms.IntegerField(label='Number of vouchers', min_value=0)

    def __init__(self, *args, **kwargs):
        super(EntryVouchersForm, self).__init__(*args, **kwargs)

        self.fields['vouchercount'].validators.append(MaxValueValidator(int(self.params['num'])))
        self.fields['vouchercount'].help_text = "Enter the number of vouchers to generate (up to %s). Please note that you cannot generate more vouchers at a later date, so please generate all the ones you want at once. If you do not want any sponsor vouchers, we ask you to please claim the number 0, so we have it for our records." % int(self.params['num'])


class EntryVouchersBackendForm(BackendSponsorshipLevelBenefitForm):
    type = forms.ChoiceField(label="Registration type", choices=[])
    num = forms.IntegerField(label="Max number of vouchers", validators=[MinValueValidator(1)])

    class_param_fields = ['type', 'num']

    def __init__(self, *args, **kwargs):
        super(EntryVouchersBackendForm, self).__init__(*args, **kwargs)
        self.fields['type'].choices = [(r.regtype, r) for r in RegistrationType.objects.filter(conference=self.conference)]


class EntryVouchers(BaseBenefit):
    @classmethod
    def get_backend_form(self):
        return EntryVouchersBackendForm

    def generate_form(self):
        return EntryVouchersForm

    def save_form(self, form, claim, request):
        if int(form.cleaned_data['vouchercount']) == 0:
            # No vouchers --> unclaim this benefit
            claim.claimjson['batchid'] = 0
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
                                   vouchervalue=base64.b64encode(os.urandom(37)).rstrip(b'=').decode('utf8'),
                                   batch=batch)
                v.save()
                vouchers.append(v)

            # Send an email about the new vouchers
            send_conference_mail(self.level.conference,
                                 request.user.email,
                                 "Entry vouchers",
                                 'confreg/mail/prepaid_vouchers.txt',
                                 {
                                     'batch': batch,
                                     'vouchers': vouchers,
                                     'conference': self.level.conference,
                                 },
                                 sender=self.level.conference.sponsoraddr,
            )

            # Finally, finish the claim
            claim.claimjson['batchid'] = batch.id
            claim.confirmed = True  # Always confirmed, they're generated after all
        return True

    def render_claimdata(self, claimedbenefit, isadmin):
        # Look up our batch
        if claimedbenefit.claimjson['batchid'] == 0:
            # This benefit has been declined
            return "Benefit was declined."

        vouchers = list(PrepaidVoucher.objects.filter(batch=claimedbenefit.claimjson['batchid']))

        generated = len(vouchers)
        used = len([1 for v in vouchers if v.usedate])

        s = StringIO.StringIO()
        s.write("<p>%s vouchers were generated, %s have been used.</p>" % (generated, used))
        s.write("<table><tr><th>Voucher code</th><th>Used by</th><th>Used at</th></tr>")
        for v in vouchers:
            s.write("<tr><td><code>{0}</code></td><td>{1}</td><td>{2}</td></tr>".format(v.vouchervalue, v.user and v.user.fullname or '', v.usedate and v.usedate or ''))
        s.write("</table>")
        return s.getvalue()

    def render_reportinfo(self, claimedbenefit):
        if claimedbenefit.claimjson['batchid'] == 0:
            return ''

        vouchers = list(PrepaidVoucher.objects.filter(batch=claimedbenefit.claimjson['batchid']))

        return '{}/{} vouchers used'.format(
            len([v for v in vouchers if v.user]),
            len(vouchers),
        )

    def can_unclaim(self, claimedbenefit):
        if claimedbenefit.claimjson['batchid'] == 0:
            # It was declined, so we can unclaim that
            return True

        batch = PrepaidBatch.objects.get(pk=claimedbenefit.claimjson['batchid'])
        if batch.prepaidvoucher_set.filter(user__isnull=False).exists():
            return False
        return True

    def validate_parameters(self):
        # Verify that the registration type being copied in actually exists
        if not RegistrationType.objects.filter(conference=self.level.conference, regtype=self.params['type']).exists():
            raise ValidationError("Registration type '{}' does not exist".format(self.params['type']))
