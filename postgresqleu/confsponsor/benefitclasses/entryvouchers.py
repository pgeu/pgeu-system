from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator, ValidationError
from django.contrib.auth.models import User

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
        self.initial['vouchercount'] = int(self.params['num'])


class EntryVouchersBackendForm(BackendSponsorshipLevelBenefitForm):
    type = forms.ChoiceField(label="Registration type", choices=[])
    num = forms.IntegerField(label="Max number of vouchers", validators=[MinValueValidator(1)])

    class_param_fields = ['type', 'num']

    def __init__(self, *args, **kwargs):
        super(EntryVouchersBackendForm, self).__init__(*args, **kwargs)
        self.fields['type'].choices = [(r.regtype, r) for r in RegistrationType.objects.filter(conference=self.conference)]


class EntryVouchers(BaseBenefit):
    can_multiclaim = False

    @classmethod
    def get_backend_form(self):
        return EntryVouchersBackendForm

    def generate_form(self):
        return EntryVouchersForm

    def save_form(self, form, claim, request):
        claim.claimjson['batchid'] = 0
        claim.claimjson['numvouchers'] = 0
        claim.claimjson['requester'] = request.user.id
        if int(form.cleaned_data['vouchercount']) == 0:
            # No vouchers --> decline this benefit
            return False
        else:
            claim.claimjson['numvouchers'] = int(form.cleaned_data['vouchercount'])
        return True

    def process_confirm(self, claim):
        # Actual number, form has been validated, so create the vouchers.
        u = User.objects.get(id=claim.claimjson['requester'])
        batch = PrepaidBatch(conference=self.level.conference,
                             regtype=RegistrationType.objects.get(conference=self.level.conference, regtype=self.params['type']),
                             buyer=u,
                             buyername="%s %s" % (u.first_name, u.last_name),
                             sponsor=claim.sponsor)
        batch.save()

        vouchers = []
        for n in range(0, claim.claimjson['numvouchers']):
            v = PrepaidVoucher(conference=self.level.conference,
                               vouchervalue=base64.b64encode(os.urandom(37)).rstrip(b'=').decode('utf8'),
                               batch=batch)
            v.save()
            vouchers.append(v)

        # Send an email about the new vouchers
        send_conference_mail(self.level.conference,
                             u.email,
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

        # Since we sent our own email, don't also send the standard confirmation one
        return False

    def render_claimdata(self, claimedbenefit, isadmin):
        if claimedbenefit.declined:
            return "Benefit was declined."
        if not claimedbenefit.confirmed:
            if isadmin:
                return "{} vouchers requested by the sponsor".format(claimedbenefit.claimjson.get('numvouchers', 0))
            else:
                return "Not confirmed yet by the organisers. Once confirmed, your vouchers will show up here."

        vouchers = list(PrepaidVoucher.objects.filter(batch=claimedbenefit.claimjson['batchid']))

        generated = len(vouchers)
        used = len([1 for v in vouchers if v.usedate])

        s = StringIO.StringIO()
        if generated == 0:
            s.write("<p>No vouchers were generated.</p>")
        elif generated == 1:
            s.write("<p>%s voucher was generated, " % (generated))
        else:
            s.write("<p>%s vouchers were generated, " % (generated))
        if generated != 0:
            if used == 0:
                s.write("none has been used.</p>")
            elif used == 1:
                s.write("%s has been used.</p>" % (used))
            else:
                s.write("%s have been used.</p>" % (used))
        s.write('<table class="table"><tr><th>Voucher code</th><th>Used by</th><th>Used at</th></tr>')
        for v in vouchers:
            s.write("<tr><td><code>{0}</code></td><td>{1}</td><td>{2}</td></tr>".format(v.vouchervalue, v.user and v.user.fullname or '', v.usedate and v.usedate or ''))
        s.write("</table>")
        return s.getvalue()

    def get_claimdata(self, claimedbenefit):
        return {
            'total': claimedbenefit.claimjson.get('numvouchers', 0),
            'used': PrepaidVoucher.objects.filter(batch=claimedbenefit.claimjson['batchid'], user__isnull=False).count(),
        }

    def render_reportinfo(self, claimedbenefit):
        if claimedbenefit.claimjson['batchid'] == 0:
            return ''

        vouchers = list(PrepaidVoucher.objects.filter(batch=claimedbenefit.claimjson['batchid']))

        return '{}/{} vouchers used'.format(
            len([v for v in vouchers if v.user]),
            len(vouchers),
        )

    def can_unclaim(self, claimedbenefit):
        if claimedbenefit.claimjson.get('batchid', 0) == 0:
            # It was declined, so we can unclaim that
            return True

        batch = PrepaidBatch.objects.get(pk=claimedbenefit.claimjson['batchid'])
        if batch.prepaidvoucher_set.filter(user__isnull=False).exists():
            # If any vouchers have been used, we can no longer unclaim.
            return False
        return True

    def process_unclaim(self, claimedbenefit):
        if claimedbenefit.claimjson['batchid'] == 0:
            return

        batch = PrepaidBatch.objects.get(pk=claimedbenefit.claimjson['batchid'])
        if batch.prepaidvoucher_set.filter(user__isnull=False).exists():
            raise Exception("An already used voucher exists in this batch!")
        batch.delete()

    def validate_parameters(self):
        # Verify that the registration type being copied in actually exists
        if not RegistrationType.objects.filter(conference=self.level.conference, regtype=self.params['type']).exists():
            raise ValidationError("Registration type '{}' does not exist".format(self.params['type']))
