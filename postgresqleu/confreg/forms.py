from django import forms
from django.forms import RadioSelect
from django.forms import ValidationError
from django.forms.utils import ErrorList
from django.core.validators import RegexValidator
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from django.utils.html import escape
from django.utils import timezone
import django.db.models
from django.db import transaction

from postgresqleu.confsponsor.models import ScannedAttendee
from .models import Conference
from .models import ConferenceRegistration, RegistrationType, Speaker
from .models import ConferenceAdditionalOption, Track, RegistrationClass
from .models import ConferenceSession, ConferenceSessionFeedback, ConferenceSessionTag
from .models import ConferenceSessionSlides
from .models import PrepaidVoucher, DiscountCode, AttendeeMail
from .models import PRIMARY_SPEAKER_PHOTO_RESOLUTION
from .util import send_conference_mail

from .regtypes import validate_special_reg_type, validate_special_reg_type_form
from .twitter import get_all_conference_social_media
from postgresqleu.util.forms import ConfirmFormMixin
from postgresqleu.util.fields import UserModelChoiceField
from postgresqleu.util.widgets import StaticTextWidget, SimpleTreeviewWidget
from postgresqleu.util.widgets import EmailTextWidget, MonospaceTextarea
from postgresqleu.util.widgets import CallForPapersSpeakersWidget
from postgresqleu.util.widgets import StaticHtmlPreviewWidget
from postgresqleu.util.db import exec_to_list
from postgresqleu.util.magic import magicdb
from postgresqleu.util.backendlookups import GeneralAccountLookup
from postgresqleu.util.time import today_conference

from postgresqleu.countries.models import Country

from datetime import timedelta
import requests


class ConferenceRegistrationForm(forms.ModelForm):
    additionaloptions = forms.ModelMultipleChoiceField(widget=forms.CheckboxSelectMultiple,
                                                       required=False,
                                                       queryset=ConferenceAdditionalOption.objects.all(),
                                                       label='Additional options')

    def __init__(self, user, *args, **kwargs):
        self.regforother = kwargs.pop('regforother', None)
        super(ConferenceRegistrationForm, self).__init__(*args, **kwargs)
        self.user = user
        self.fields['regtype'].queryset = RegistrationType.objects.select_related('conference', 'conference__vat_registrations').filter(conference=self.instance.conference).order_by('sortkey')
        self.fields['photoconsent'].required = True
        for f in self.instance.conference.remove_fields:
            if f in self.fields:
                del self.fields[f]

        if self.regforother:
            self.fields['email'].widget.attrs['readonly'] = True
        self.fields['additionaloptions'].queryset = ConferenceAdditionalOption.objects.select_related('conference', 'conference__vat_registrations').filter(
            conference=self.instance.conference, public=True)
        self.fields['country'].choices = self._get_country_choices()

        if not self.regforother:
            self.intro_html = mark_safe('<p>You are currently making a registration for account<br/><i>{0} ({1} {2} &lt;{3}&gt;).</i></p>'.format(escape(self.user.username), escape(self.user.first_name), escape(self.user.last_name), escape(self.user.email)))
        else:
            self.intro_html = mark_safe('<p>You are currently editing a registration for somebody other than yourself.</p>')

    def _get_country_choices(self):
        yield (None, 'Prefer not to say')

        def _common_countries():
            for iso, prn in exec_to_list("WITH t AS (SELECT iso, printable_name FROM country c INNER JOIN (SELECT country_id FROM confreg_conferenceregistration r WHERE r.conference_id=%(confid)s AND payconfirmedat IS NOT NULL AND canceledat IS NULL AND country_id IS NOT NULL UNION ALL SELECT country_id FROM confreg_conference_initial_common_countries WHERE conference_id=%(confid)s) x ON c.iso=x.country_id GROUP BY c.iso ORDER BY count(iso) DESC LIMIT 8) SELECT iso, printable_name FROM t ORDER BY printable_name", {
                    'confid': self.instance.conference.id,
            }):
                yield (iso, prn)

        def _all_countries():
            for c in Country.objects.order_by('printable_name'):
                yield (c.iso, c.printable_name)

        cc = list(_common_countries())
        if cc:
            yield ('Common countries', cc)

        yield ('All countries', list(_all_countries()))

    def clean_regtype(self):
        newval = self.cleaned_data.get('regtype')
        if self.instance and newval == self.instance.regtype:
            # Registration type not changed, so it's ok to save
            # (we don't want to prohibit other edits for somebody who has
            #  an already-made registration with an expired registration type)
            return newval

        if newval and not newval.active:
            raise forms.ValidationError('Registration type "%s" is currently not available.' % newval)

        if newval and newval.activeuntil and newval.activeuntil <= today_conference():
            raise forms.ValidationError('Registration type "%s" was only available until %s.' % (newval, newval.activeuntil))

        if self.instance and self.instance.payconfirmedat:
            raise forms.ValidationError('You cannot change type of registration once your payment has been confirmed!')

        if newval and newval.specialtype:
            validate_special_reg_type(newval.specialtype, self.instance)

        return newval

    def clean_email(self):
        e = self.cleaned_data.get('email').lower()
        # Is there another non-canceled registration made for this email?
        if ConferenceRegistration.objects.exclude(id=self.instance.id).filter(email=e, conference=self.instance.conference, canceledat__isnull=True).exists():
            raise ValidationError('There is already a registration made with this email address')
        return e

    def clean_vouchercode(self):
        newval = self.cleaned_data.get('vouchercode')
        if newval == '':
            return newval

        try:
            v = PrepaidVoucher.objects.get(vouchervalue=newval, conference=self.instance.conference)
            if v.usedate:
                raise forms.ValidationError('This voucher has already been used')
            r = ConferenceRegistration.objects.filter(vouchercode=newval,
                                                      conference=self.instance.conference)
            if r:
                if r[0].id != self.instance.id:
                    raise forms.ValidationError('This voucher is already pending on another registration')
        except PrepaidVoucher.DoesNotExist:
            # It could be that it's a discount code
            try:
                c = DiscountCode.objects.get(code=newval, conference=self.instance.conference)
                if c.is_invoiced:
                    raise forms.ValidationError('This discount code is not valid anymore.')
                if c.validuntil and c.validuntil < today_conference():
                    raise forms.ValidationError('This discount code has expired.')
                if c.maxuses > 0:
                    if c.registrations.count() >= c.maxuses:
                        raise forms.ValidationError('All allowed instances of this discount code have been used.')

                required_regtypes = c.requiresregtype.all()
                if required_regtypes:
                    # If the list is empty, any goes. But if there's something
                    # in the list, we have to enforce it.
                    if not self.cleaned_data.get('regtype') in required_regtypes:
                        raise forms.ValidationError("This discount code is only valid for registration type(s): {0}".format(", ".join([r.regtype for r in required_regtypes])))

                selected = self.cleaned_data.get('additionaloptions') or ()
                for o in c.requiresoption.all():
                    if o not in selected:
                        raise forms.ValidationError("This discount code requires the option '%s' to be picked." % o)

            except DiscountCode.DoesNotExist:
                raise forms.ValidationError('This voucher or discount code was not found')

        return newval

    def compare_options(self, a, b):
        # First check if the sizes are the same
        if len(a) != len(b):
            return False

        # Then do a very expensive one-by-one check
        for x in a:
            found = False
            for y in b:
                if x.pk == y.pk:
                    found = True
                    break
            if not found:
                # Entry in a not found in b, give up
                return False

        # All entires in a were in b, and the sizes were the same..
        return True

    def clean_additionaloptions(self):
        newval = self.cleaned_data.get('additionaloptions')

        if self.instance and self.instance.pk:
            oldval = list(self.instance.additionaloptions.all())
        else:
            oldval = ()

        if self.instance and self.compare_options(newval, oldval):
            # Additional options not changed, so keep allowing them
            return newval

        # Check that the new selection is available by doing a count
        # We only look at the things that have been *added*
        for option in set(newval).difference(oldval):
            if option.maxcount == -1:
                raise forms.ValidationError("The option \"%s\" is currently not available." % option.name)
            if option.maxcount > 0:
                # This option has a limit on the number of people
                # Count how many others have it. The difference we took on
                # the sets above means we only check this when *this*
                # registration doesn't have the option, and thus the count
                # will always increase by one if we save this.
                current_count = option.conferenceregistration_set.count() + option.pendingadditionalorder_set.filter(payconfirmedat__isnull=True).count()
                if current_count + 1 > option.maxcount:
                    raise forms.ValidationError("The option \"%s\" is no longer available due to too many signups." % option.name)

        for option in newval:
            # Check if something mutually exclusive is included
            for x in option.mutually_exclusive.all():
                if x in newval:
                    raise forms.ValidationError('The option "%s" cannot be ordered at the same time as "%s".' % (option.name, x.name))

        # Check if the registration has been confirmed
        if self.instance and self.instance.payconfirmedat:
            raise forms.ValidationError('You cannot change your additional options once your payment has been confirmed! If you need to make changes, please contact the conference organizers via email')

        # Yeah, it's ok
        return newval

    def clean(self):
        # At the form level, validate anything that has references between
        # different fields, since they are not saved until we get here.
        # Note that if one of those fields have failed validation on their
        # own, they will not be present in cleaned_data.
        cleaned_data = super(ConferenceRegistrationForm, self).clean()

        if cleaned_data.get('vouchercode', None):
            # We know it's there, and that it exists - but is it for the
            # correct type of registration?
            errs = []
            try:
                v = PrepaidVoucher.objects.get(vouchervalue=cleaned_data['vouchercode'],
                                               conference=self.instance.conference)
                if 'regtype' not in cleaned_data:
                    errs.append('Invalid registration type specified')
                    raise ValidationError('An invalid registration type has been selected')
                if v.batch.regtype != cleaned_data['regtype']:
                    errs.append('The specified voucher is only usable for registrations of type "%s"' % v.batch.regtype)
            except PrepaidVoucher.DoesNotExist:
                # This must have been a discount code :)
                try:
                    DiscountCode.objects.get(code=cleaned_data['vouchercode'],
                                             conference=self.instance.conference)
                    # Validity of the code has already been validated, and it's not tied
                    # to a specific one, so as long as it exists, we're good to go.
                except DiscountCode.DoesNotExist:
                    errs.append('Specified voucher or discount code does not exist')

            if errs:
                self._errors['vouchercode'] = ErrorList(errs)

        if cleaned_data.get('regtype', None):
            if cleaned_data['regtype'].requires_option.exists():
                regtype = cleaned_data['regtype']
                found = False
                if cleaned_data.get('additionaloptions', None):
                    for x in regtype.requires_option.all():
                        if x in cleaned_data['additionaloptions']:
                            found = True
                            break
                if not found:
                    self._errors['regtype'] = 'Registration type "%s" requires at least one of the following additional options to be picked: %s' % (regtype, ", ".join([x.name for x in regtype.requires_option.all()]))

            if cleaned_data['regtype'].specialtype:
                for errfld, errmsg in validate_special_reg_type_form(cleaned_data['regtype'].specialtype, self.instance, cleaned_data):
                    self.add_error(errfld, errmsg)

        if cleaned_data.get('additionaloptions', None) and 'regtype' in cleaned_data:
            regtype = cleaned_data['regtype']
            errs = []
            for ao in cleaned_data['additionaloptions']:
                if msg := ao.verify_available_to(regtype, self.instance if self.instance.pk else None):
                    self.add_error('additionaloptions', msg)

        return cleaned_data

    class Meta:
        model = ConferenceRegistration
        fields = ('regtype', 'firstname', 'lastname', 'email', 'company', 'address',
                  'country', 'phone', 'shirtsize', 'dietary', 'additionaloptions',
                  'twittername', 'nick', 'pronouns', 'badgescan', 'shareemail', 'photoconsent', 'vouchercode',
        )
        widgets = {
            'photoconsent': forms.Select(choices=((None, ''), (True, 'I consent to having my photo taken'), (False, "I don't want my photo taken"))),
            'badgescan': forms.Select(choices=((True, 'Allow sponsors to scan my badge'), (False, "Don't allow sponsors to scan my badge"))),
        }

    @property
    def fieldsets(self):
        # Return a set of fields used for our rendering
        conf = self.instance.conference

        fields = ['regtype', 'firstname', 'lastname', 'company', 'address', 'country', 'email']
        if conf.askpronouns:
            fields.append('pronouns')
        if conf.asktwitter:
            fields.append('twittername')
        if conf.asknick:
            fields.append('nick')
        yield {'id': 'personal_information',
               'legend': 'Personal information',
               'introhtml': self.intro_html,
               'fields': [self[x] for x in fields],
               }

        if conf.asktshirt or conf.askfood or conf.askshareemail:
            fields = []
            if conf.asktshirt:
                fields.append(self['shirtsize'])
            if conf.askfood:
                fields.append(self['dietary'])
            if conf.askshareemail:
                fields.append(self['shareemail'])
            yield {'id': 'conference_info',
                   'legend': 'Conference information',
                   'fields': fields}

        if conf.askphotoconsent or conf.askbadgescan:
            fields = []
            if conf.askphotoconsent:
                fields.append(self['photoconsent'])
            if conf.askbadgescan:
                fields.append(self['badgescan'])
            yield {'id': 'consent_info',
                   'legend': 'Consent',
                   'fields': fields,
            }

        if conf.conferenceadditionaloption_set.filter(public=True).exists():
            yield {'id': 'additional_options',
                   'legend': 'Additional options',
                   'introproperty': 'system.reg.additionaloptionsintro',
                   'fields': [self['additionaloptions'], ],
                   }

        yield {'id': 'voucher_codes',
               'legend': 'Voucher codes',
               'intro': 'If you have a voucher or discount code, enter it in this field. If you do not have one, just leave the field empty.',
               'introproperty': 'system.reg.voucherintro',
               'fields': [self['vouchercode'], ],
        }


class RegistrationChangeForm(forms.ModelForm):
    def __init__(self, allowedit, *args, **kwargs):
        super(RegistrationChangeForm, self).__init__(*args, **kwargs)
        self.allowedit = allowedit
        self.fields['photoconsent'].required = True
        for f in self.instance.conference.remove_fields:
            if f in self.fields:
                del self.fields[f]
        if not self.allowedit:
            for f in self.fields:
                if f not in self.Meta.unlocked_fields:
                    self.fields[f].widget.attrs['readonly'] = 'true'

    class Meta:
        model = ConferenceRegistration
        fields = ('shirtsize', 'dietary', 'twittername', 'nick', 'badgescan', 'shareemail', 'photoconsent', )
        unlocked_fields = ('badgescan', )
        widgets = {
            'photoconsent': forms.Select(choices=((None, ''), (True, 'I consent to having my photo taken'), (False, "I don't want my photo taken"))),
            'badgescan': forms.Select(choices=((True, 'Allow sponsors to scan my badge'), (False, "Don't allow sponsors to scan my badge"))),
        }

    def clean_badgescan(self):
        newval = self.cleaned_data.get('badgescan')
        if self.instance.badgescan and not newval:
            # Change from allowed -> disallowed is only allowed (!) if no sponsor has already
            # scanned this badge.
            if ScannedAttendee.objects.filter(attendee=self.instance).exists():
                raise ValidationError("This setting cannot be changed since your badge has already been scanned by at least one sponsor.")

        return newval

    def clean(self):
        d = super(RegistrationChangeForm, self).clean()
        if not self.allowedit:
            for k in d.keys():
                if k not in self.Meta.unlocked_fields:
                    d[k] = self.initial[k]
        return d


class RequestCancelForm(forms.Form):
    cancelreason = forms.CharField(label="Reason for cancelation", required=False,
                                   help_text="Giving the reason is optional, but helps us in our planning work")
    confirm = forms.BooleanField(label="Confirm", required=True)


rating_choices = (
    (1, '1 (Worst)'),
    (2, '2'),
    (3, '3'),
    (4, '4'),
    (5, '5 (Best)'),
    (0, 'N/A'),
)


class NewMultiRegForm(forms.Form):
    email = forms.EmailField(required=True)

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        super(NewMultiRegForm, self).__init__(*args, **kwargs)

    def clean_email(self):
        e = self.cleaned_data.get('email').lower()

        if ConferenceRegistration.objects.filter(conference=self.conference, email=e).exists():
            raise ValidationError("A registration for this email address already exists. For privacy reasons, management of a registration cannot be transferred.")
        return e


class MultiRegInvoiceForm(forms.Form):
    recipient = forms.CharField(max_length=100, required=True)
    address = forms.CharField(widget=forms.widgets.Textarea, required=True)
    policyconfirm = forms.CharField(widget=forms.widgets.HiddenInput, required=True, initial='1')


class ConferenceSessionFeedbackForm(forms.ModelForm):
    topic_importance = forms.ChoiceField(widget=RadioSelect, choices=rating_choices, label='Importance of the topic')
    content_quality = forms.ChoiceField(widget=RadioSelect, choices=rating_choices, label='Quality of the content')
    speaker_knowledge = forms.ChoiceField(widget=RadioSelect, choices=rating_choices, label='Speakers knowledge of the subject')
    speaker_quality = forms.ChoiceField(widget=RadioSelect, choices=rating_choices, label='Speakers presentation skills')

    class Meta:
        model = ConferenceSessionFeedback
        fields = ('topic_importance', 'content_quality', 'speaker_knowledge', 'speaker_quality', 'speaker_feedback', 'conference_feedback')


class ConferenceFeedbackForm(forms.Form):
    # Very special dynamic form. It's ugly, but hey, it works
    def __init__(self, *args, **kwargs):
        questions = kwargs.pop('questions')
        responses = kwargs.pop('responses')

        super(ConferenceFeedbackForm, self).__init__(*args, **kwargs)

        # Now add our custom fields
        for q in questions:
            if q.isfreetext:
                if q.textchoices:
                    self.fields['question_%s' % q.id] = forms.ChoiceField(widget=RadioSelect,
                                                                          choices=[(x, x) for x in q.textchoices.split(";")],
                                                                          label=q.question,
                                                                          initial=self.get_answer_text(responses, q.id))
                else:
                    self.fields['question_%s' % q.id] = forms.CharField(widget=forms.widgets.Textarea,
                                                                        label=q.question,
                                                                        required=False,
                                                                        initial=self.get_answer_text(responses, q.id))
            else:
                self.fields['question_%s' % q.id] = forms.ChoiceField(widget=RadioSelect,
                                                                      choices=rating_choices,
                                                                      label=q.question,
                                                                      initial=self.get_answer_num(responses, q.id))

            # Overload fieldset on help_text. Really really really ugly, but a way to get the fieldset
            # out into the form without having to subclass things.
            self.fields['question_%s' % q.id].help_text = q.newfieldset

    def get_answer_text(self, responses, id):
        for r in responses:
            if r.question_id == id:
                return r.textanswer
        return ""

    def get_answer_num(self, responses, id):
        for r in responses:
            if r.question_id == id:
                return r.rateanswer
        return -1


class SpeakerProfileForm(forms.ModelForm):
    email = forms.CharField(
        max_length=100, required=False,
        help_text='The email address is retrieved from the account you are logged in with.',
        widget=StaticTextWidget(),
    )

    class Meta:
        model = Speaker
        fields = ('fullname', 'company', 'abstract', 'photo512')

    field_order = ['fullname', 'email', 'company', 'abstract', 'photo512']

    def __init__(self, user, *args, **kwargs):
        self.user = user

        super(SpeakerProfileForm, self).__init__(*args, **kwargs)

        self.initial['email'] = self.instance.user.email if self.instance.user else self.user.email

        self.fields['photo512'].help_text = 'Photo will be rescaled to {}x{} pixels. We reserve the right to make minor edits to speaker photos if necessary'.format(*PRIMARY_SPEAKER_PHOTO_RESOLUTION)

        for classname, social, impl in sorted(get_all_conference_social_media('speaker'), key=lambda x: x[1]):
            self.fields['social_{}'.format(social)] = forms.CharField(label="{} name".format(social.title()), max_length=250, required=False)
            self.fields['social_{}'.format(social)].initial = self.instance.attributes.get('social', {}).get(social, '')

    def clean(self):
        cleaned_data = super().clean()

        for classname, social, impl in sorted(get_all_conference_social_media('speaker'), key=lambda x: x[1]):
            fn = 'social_{}'.format(social)
            if cleaned_data.get(fn, None):
                try:
                    cleaned_data[fn] = impl.clean_identifier_form_value('speaker', cleaned_data[fn])
                except ValidationError as v:
                    self.add_error(fn, v)

        return cleaned_data

    def clean_fullname(self):
        if not self.cleaned_data['fullname'].strip():
            raise ValidationError("Your full name must be given. This will be used both in the speaker profile and in communications with the conference organizers.")
        return self.cleaned_data['fullname']

    def save(self, *args, **kwargs):
        obj = super().save(*args, **kwargs)
        if 'social' not in obj.attributes:
            obj.attributes['social'] = {}

        for classname, social, impl in sorted(get_all_conference_social_media('speaker'), key=lambda x: x[1]):
            v = self.cleaned_data['social_{}'.format(social)]
            if v:
                obj.attributes['social'][social] = v
            elif social in obj.attributes['social']:
                del obj.attributes['social'][social]

        obj.save(update_fields=['attributes'])
        return obj


class CallForPapersForm(forms.ModelForm):
    class Meta:
        model = ConferenceSession
        fields = ('title', 'abstract', 'skill_level', 'track', 'tags', 'recordingconsent', 'speaker', 'submissionnote')

    def __init__(self, currentspeaker, *args, **kwargs):
        self.currentspeaker = currentspeaker

        super(CallForPapersForm, self).__init__(*args, **kwargs)

        # Extra speakers should at this point only contain the ones that are already
        # there. More are added by the javascript code, but we don't want to populate
        # with a list of everything (too easy to scrape as well).
        if self.instance.id:
            vals = [s.pk for s in self.instance.speaker.all()]
        else:
            vals = [s.pk for s in self.initial['speaker']]
        # We may also have received a POST that contains new speakers not already on this
        # record. In this case, we have to add them as possible values, so the validation
        # doesn't fail.
        if 'data' in kwargs and 'speaker' in kwargs['data']:
            vals.extend([int(x) for x in kwargs['data'].getlist('speaker')])

        self.fields['speaker'].widget = CallForPapersSpeakersWidget(self.instance.conference)
        self.fields['speaker'].queryset = Speaker.objects.defer('photo', 'photo512').filter(pk__in=vals).annotate(
            iscurrent=django.db.models.Case(django.db.models.When(pk=currentspeaker.pk, then=True), output_field=django.db.models.BooleanField())
        ).order_by('iscurrent', 'fullname')
        self.fields['speaker'].required = True

        if not self.instance.conference.skill_levels:
            del self.fields['skill_level']

        if self.instance.conference.callforpaperstags:
            self.fields['tags'].widget = forms.CheckboxSelectMultiple()
            self.fields['tags'].queryset = ConferenceSessionTag.objects.filter(conference=self.instance.conference)
            self.fields['tags'].label_from_instance = lambda x: x.tag
            self.fields['tags'].required = False
        else:
            del self.fields['tags']

        if not self.instance.conference.callforpapersrecording:
            del self.fields['recordingconsent']
        else:
            # Use TypedChoiceField with RadioSelect to force explicit choice
            self.fields['recordingconsent'] = forms.TypedChoiceField(
                choices=(
                    ('True', 'I give my consent for the conference organisers to record my presentation and give permission for them to distribute the recording under the license of their choice.'),
                    ('False', "I don't consent to recording of my presentation."),
                ),
                coerce=lambda x: x == 'True',
                required=True,
                widget=forms.RadioSelect,
                label='Recording consent',
            )
            # Set initial value if editing existing session
            if self.instance.id and self.instance.recordingconsent is not None:
                self.fields['recordingconsent'].initial = 'True' if self.instance.recordingconsent else 'False'

        if not self.instance.conference.track_set.filter(incfp=True).count() > 0:
            del self.fields['track']
        else:
            # Special case -- if a track already picked is no longer flagged as "incfp", it means that this particular
            # track has been closed. But we want to still allow editing of *other* details, so juste create a set
            # of tracks that includes just this one.
            if self.instance.track and not self.instance.track.incfp:
                self.fields['track'].queryset = Track.objects.filter(conference=self.instance.conference, pk=self.instance.track.pk).order_by('sortkey', 'trackname')
                self.fields['track'].empty_label = None
            else:
                self.fields['track'].queryset = Track.objects.filter(conference=self.instance.conference, incfp=True).order_by('sortkey', 'trackname')

    def clean_abstract(self):
        abstract = self.cleaned_data.get('abstract')
        if len(abstract) < 30:
            raise ValidationError("Submitted abstract is too short (must be at least 30 characters)")
        return abstract

    def clean_track(self):
        if not self.cleaned_data.get('track'):
            raise ValidationError("Please choose the track that is the closest match to your talk")
        return self.cleaned_data.get('track')

    def clean_speaker(self):
        if self.currentspeaker not in self.cleaned_data.get('speaker'):
            raise ValidationError("You cannot remove yourself as a speaker!")
        if self.instance.conference.callforpapersmaxsubmissions > 0:
            # Inefficient to loop over them, but there will never be many, so we're lazy.
            for s in self.cleaned_data.get('speaker'):
                if s == self.currentspeaker:
                    continue
                if self.instance.conference.conferencesession_set.filter(speaker=s).exclude(status=6).count() >= self.instance.conference.callforpapersmaxsubmissions:
                    raise ValidationError(
                        "Speaker {} already has too many submissions for this conference.".format(s)
                    )

        return self.cleaned_data.get('speaker')

    def clean(self):
        d = super().clean()
        if self.instance.conference.callforpapersmaxsubmissions > 0:
            if not self.instance.id:
                # If this is a new submission, check the count
                speaker = self.initial['speaker'][0]
                count = self.instance.conference.conferencesession_set.filter(speaker=speaker).exclude(status=6).count()
                if count >= self.instance.conference.callforpapersmaxsubmissions:
                    self.add_error(
                        'title',
                        'This conference allows a maximum {}  submissions per speaker, and you have already submitted {}.'.format(
                            self.instance.conference.callforpapersmaxsubmissions,
                            count,
                        )
                    )
        return d

    def save(self):
        with transaction.atomic():
            if self.instance.pk:
                oldobj = ConferenceSession.objects.get(pk=self.instance.pk)
                oldspeakerids = [s.id for s in oldobj.speaker.all()]
            else:
                oldspeakerids = [self.currentspeaker.id]

            super().save()

            addedspeakers = self.instance.speaker.exclude(id__in=oldspeakerids)
            for spk in addedspeakers:
                send_conference_mail(
                    self.instance.conference,
                    spk.user.email,
                    "Submitted session '{}'".format(self.instance.title),
                    'confreg/mail/secondary_speaker_added.txt',
                    {
                        'conference': self.instance.conference,
                        'session': self.instance,
                        'speaker': spk,
                        'addingspeaker': self.currentspeaker,
                    },
                    receivername=spk.fullname,
                )


class SessionCopyField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return "{0}: {1} ({2})".format(obj.conference, obj.title, obj.status_string)


class CallForPapersCopyForm(forms.Form):
    sessions = SessionCopyField(widget=forms.CheckboxSelectMultiple,
                                required=True,
                                queryset=ConferenceSession.objects.filter(id=-1),
                                label='Select sessions')

    def __init__(self, conference, speaker, *args, **kwargs):
        self.conference = conference
        self.speaker = speaker
        super(CallForPapersCopyForm, self).__init__(*args, **kwargs)
        self.fields['sessions'].queryset = ConferenceSession.objects.select_related('conference').filter(speaker=speaker).exclude(conference=conference).order_by('-conference__startdate', 'title')

    def clean_sessions(self):
        s = self.cleaned_data['sessions']
        if self.conference.callforpapersmaxsubmissions > 0:
            already = self.conference.conferencesession_set.filter(speaker=self.speaker).exclude(status=6).count()
            added = s.count()
            if already + added > self.conference.callforpapersmaxsubmissions:
                raise ValidationError('This conference allows a maximum {}  submissions per speaker, and you have already submitted {}. You cannot add {} more.'.format(
                    self.conference.callforpapersmaxsubmissions,
                    already,
                    added,
                ))

        return s


class SessionSlidesUrlForm(forms.Form):
    url = forms.URLField(label='URL', required=False, max_length=1000)

    def clean_url(self):
        if not self.cleaned_data.get('url', None):
            return
        u = self.cleaned_data['url']
        # Ping out to the URL but with a very short timeout
        try:
            r = requests.get(u, timeout=2)
            if r.status_code != 200:
                raise ValidationError("URL returns status %s" % r.status_code)
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError("URL does not validate")
        return u


class SessionSlidesFileForm(forms.Form):
    f = forms.FileField(label='Upload', required=False)
    license = forms.BooleanField(label='License', required=False, help_text='I confirm that this this file may be redistributed by the conference website')

    def clean_f(self):
        if not self.cleaned_data.get('f', None):
            return
        f = self.cleaned_data['f']

        maxnamelen = ConferenceSessionSlides._meta.get_field('name').max_length
        if len(f.name) > maxnamelen:
            raise ValidationError("Filenames can't be longer than {} characters.".format(maxnamelen))
        if not f.name.endswith('.pdf'):
            raise ValidationError("Uploaded files must have a filename ending in PDF")

        mtype = magicdb.buffer(f.read())
        if not mtype.startswith('application/pdf'):
            raise ValidationError("Uploaded files must be mime type PDF only, not %s" % mtype)
        f.seek(0)
        return f

    def clean(self):
        cleaned_data = super(SessionSlidesFileForm, self).clean()
        if cleaned_data.get('f', None) and not cleaned_data['license']:
            self.add_error('license', 'You must accept the license')
        return cleaned_data


class PrepaidCreateForm(ConfirmFormMixin, forms.Form):
    regtype = forms.ModelChoiceField(label="Registration type", queryset=RegistrationType.objects.filter(id=-1))
    count = forms.IntegerField(label="Number of vouchers", min_value=1, max_value=100)
    buyer = forms.ModelChoiceField(queryset=User.objects.filter(pk=-1).order_by('username'), help_text="Pick the user who bought the batch. If he/she does not have an account, pick your own userid")
    invoice = forms.BooleanField(help_text="Automatically create invoice for these vouchers and send it to the person ordering them.", required=False)
    invoiceaddress = forms.CharField(label="Invoice address", help_text="Complete address to put on invoice. Note that the name of the buyer is prepended to this!", required=False, widget=MonospaceTextarea)

    confirm_what = 'create vouchers'
    confirm_text = 'Please confirm that the chosen registration type and count are correct (there is no undo past this point, the vouchers will be created!'

    selectize_multiple_fields = {
        'buyer': GeneralAccountLookup(),
    }

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        super(PrepaidCreateForm, self).__init__(*args, **kwargs)
        self.fields['regtype'].queryset = RegistrationType.objects.filter(conference=conference)
        self.fields['buyer'].label_from_instance = lambda x: '{0} {1} <{2}> ({3})'.format(x.first_name, x.last_name, x.email, x.username)

        if 'data' in kwargs and 'buyer' in kwargs['data']:
            self.fields['buyer'].queryset = User.objects.filter(pk__in=kwargs['data'].getlist('buyer'))

    def clean(self):
        cleaned_data = super(PrepaidCreateForm, self).clean()
        if self.cleaned_data.get('invoice', False):
            if not self.cleaned_data.get('invoiceaddress'):
                self.add_error('invoiceaddress', 'Invoice address must be specified if invoice creation is selected!')
        else:
            if self.cleaned_data.get('invoiceaddress'):
                self.add_error('invoiceaddress', 'Invoice address should not be specified unless inovice creation is eelected!')
        return cleaned_data


class AttendeeMailForm(forms.Form):
    regclasses = forms.ModelMultipleChoiceField(
        queryset=RegistrationClass.objects.all(),
        required=False,
        label="Registration classes",
        widget=forms.CheckboxSelectMultiple,
    )
    addopts = forms.ModelMultipleChoiceField(
        queryset=ConferenceAdditionalOption.objects.all(),
        required=False,
        label="Additional options",
        widget=forms.CheckboxSelectMultiple,
    )
    volunteers = forms.BooleanField(
        required=False,
        label="To volunteers",
    )
    checkin = forms.BooleanField(
        required=False,
        label="To check-in processors",
    )

    def regclass_label(self, obj):
        return "{0} (contains {1}; total {2} registrations)".format(
            obj.regclass,
            ", ".join([t.regtype for t in obj.registrationtype_set.all()]),
            ConferenceRegistration.objects.filter(conference=self.conference,
                                                  payconfirmedat__isnull=False,
                                                  canceledat__isnull=True,
                                                  regtype__regclass=obj).count(),
        )

    def addopts_label(self, obj):
        return "{0} (total {1} registrations)".format(
            obj.name,
            ConferenceRegistration.objects.filter(conference=self.conference,
                                                  payconfirmedat__isnull=False,
                                                  canceledat__isnull=True,
                                                  additionaloptions=obj).count()
        )

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        super(AttendeeMailForm, self).__init__(*args, **kwargs)

        self.fields['regclasses'].queryset = RegistrationClass.objects.filter(conference=self.conference)
        self.fields['regclasses'].label_from_instance = self.regclass_label

        self.fields['addopts'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.conference)
        self.fields['addopts'].label_from_instance = self.addopts_label

    def clean(self):
        d = super().clean()

        if not any((d['volunteers'], d['checkin'], d['regclasses'], d['addopts'])):
            raise ValidationError("Must specify at least one type of destination")

        return d

    def get_idlist(self):
        yield from ('c{}'.format(c.id) for c in self.cleaned_data['regclasses'])
        yield from ('a{}'.format(a.id) for a in self.cleaned_data['addopts'])
        if self.cleaned_data['volunteers']:
            yield 'xv'
        if self.cleaned_data['checkin']:
            yield 'xc'


class SendExternalEmailForm(forms.Form):
    sendername = forms.CharField(required=False, widget=StaticTextWidget(), label="Sender name")
    sender = forms.ChoiceField()
    recipient = forms.EmailField()
    recipientname = forms.CharField(label="Recipient name", validators=[
        RegexValidator('[,=]', inverse_match=True, message='Invalid character in name'),
    ])

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        super().__init__(*args, **kwargs)

        # We want to show a sendername field to make it clear to the user what it will be,
        # even if it cannot be changed.
        self.fields['sendername'].initial = self.conference.conferencename
        if self.data:
            self.data = self.data.copy()
            self.data['sendername'] = self.conference.conferencename

        self.fields['sender'].choices = [
            (1, 'Contact address: {}'.format(conference.contactaddr)),
            (2, 'Sponsor address: {}'.format(conference.sponsoraddr)),
        ]


class WaitlistOfferForm(forms.Form):
    hours = forms.IntegerField(min_value=1, max_value=240, label='Offer valid for (hours)', initial=48)
    until = forms.DateTimeField(label='Offer valid until', initial=(timezone.now() + timedelta(hours=48)).strftime('%Y-%m-%d %H:%M'))


class WaitlistConfirmForm(forms.Form):
    timespec = forms.DateTimeField(widget=forms.HiddenInput)
    reglist = forms.CharField(widget=forms.HiddenInput)
    confirm = forms.BooleanField(required=True, label="Confirm", help_text="Confirm sending offer")


class WaitlistSendmailForm(forms.Form):
    TARGET_ALL = 0
    TARGET_OFFERS = 1
    TARGET_NOOFFERS = 2

    TARGET_CHOICES = (
        (TARGET_ALL, 'All attendees on waitlist'),
        (TARGET_OFFERS, 'Only attendees with active offers'),
        (TARGET_NOOFFERS, 'Only attendees without active offers'),
    )

    waitlist_target = forms.ChoiceField(required=True, choices=TARGET_CHOICES)

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        super(WaitlistSendmailForm, self).__init__(*args, **kwargs)


class TransferRegForm(forms.Form):
    transfer_from = forms.ModelChoiceField(ConferenceRegistration.objects.filter(id=-1))
    transfer_to = forms.ModelChoiceField(ConferenceRegistration.objects.filter(id=-1))
    create_invoice = forms.BooleanField(required=False, help_text="Create an invoice for this transfer, and perform the transfer only once the invoice is paid?")
    invoice_recipient = UserModelChoiceField(User.objects.all(), required=False, label="Invoice recipient user", help_text="Not required but if specified it will attach the invoice to this account so it can be viewed in the users inovice list")
    invoice_name = forms.CharField(required=False, label="Invoice recipient name", help_text="Name of the recipient of the invoice")
    invoice_email = forms.EmailField(required=False, label="Invoice recipient email", help_text="E-mail to send the invoice to")
    invoice_address = forms.CharField(widget=MonospaceTextarea, required=False)
    invoice_autocancel = forms.IntegerField(required=False, label="Invoice autocancel hours", help_text="Automatically cancel invoice after this many hours",
                                            validators=[django.core.validators.MinValueValidator(0)])
    confirm = forms.BooleanField(help_text="Confirm that you want to transfer the registration with the given steps!", required=False)

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        super(TransferRegForm, self).__init__(*args, **kwargs)
        self.initial['invoice_autocancel'] = conference.invoice_autocancel_hours
        self.fields['transfer_from'].queryset = ConferenceRegistration.objects.select_related('conference').filter(conference=conference, payconfirmedat__isnull=False, canceledat__isnull=True, transfer_from_reg__isnull=True)
        self.fields['transfer_to'].queryset = ConferenceRegistration.objects.select_related('conference').filter(conference=conference, payconfirmedat__isnull=True, canceledat__isnull=True, bulkpayment__isnull=True)
        if not ('transfer_from' in self.data and 'transfer_to' in self.data):
            del self.fields['confirm']
        if not conference.transfer_cost:
            del self.fields['create_invoice']
            del self.fields['invoice_recipient']
            del self.fields['invoice_name']
            del self.fields['invoice_email']
            del self.fields['invoice_address']
        else:
            # For invoice recipient, we list only the selected one if there is one (but all users are valid)
            if 'data' in kwargs and 'invoice_recipient' in kwargs['data']:
                val = kwargs['data'].get('invoice_recipient') or None
            else:
                val = None
            self.fields['invoice_recipient'].queryset = User.objects.filter(pk=val)

    def remove_confirm(self):
        del self.fields['confirm']

    def clean(self):
        cleaned_data = super().clean()
        invoice_fields = ['invoice_name', 'invoice_email', 'invoice_address']
        if cleaned_data.get('create_invoice', False):
            for f in invoice_fields:
                if not cleaned_data.get(f, None):
                    self.add_error(f, 'This field is required when creating an invoice')
        else:
            for f in invoice_fields:
                if self.cleaned_data.get(f, None):
                    self.add_error(f, 'This field cannot be specified unless creating an invoice')

        return cleaned_data


class CrossConferenceMailForm(forms.Form):
    senderaddr = forms.ChoiceField(required=True, label="Sender address")
    sendername = forms.CharField(min_length=5, required=True, label="Sender name")
    include = forms.CharField(widget=forms.widgets.HiddenInput(), required=False)
    exclude = forms.CharField(widget=forms.widgets.HiddenInput(), required=False)
    subject = forms.CharField(min_length=10, max_length=80, required=True)
    text = forms.CharField(min_length=30, required=True, widget=EmailTextWidget)
    available_fields = django.forms.CharField(required=False,
                                              help_text="These fields are available as {{field}} in the template")
    textpreview = django.forms.CharField(label="Text message", widget=StaticTextWidget(monospace=True), required=False)
    htmlpreview = django.forms.CharField(label="HTML message", widget=StaticHtmlPreviewWidget(), required=False)

    @property
    def dynamic_preview_fields(self):
        if self.is_confirm:
            return []
        else:
            return ['text', ]

    def __init__(self, user, is_confirm, *args, **kwargs):
        self.user = user
        self.htmlpreview = kwargs.pop('htmlpreview', None)
        self.textpreview = kwargs.pop('textpreview', None)
        self.is_confirm = is_confirm

        super(CrossConferenceMailForm, self).__init__(*args, **kwargs)

        self.fields['available_fields'].widget = SimpleTreeviewWidget(treedata={x: None for x in ['name', 'email', 'token']})

        conferences = Conference.objects.select_related('series').all()
        if not self.user.is_superuser:
            conferences = conferences.filter(series__administrators=self.user)
        conferences = conferences.order_by('series__name', '-startdate')

        choices = []
        currentgroup = None
        lastseries = None

        def _unwrap_addresses(group):
            return [group[0], [(a, a) for a in sorted(list(group[1]))]]

        for conf in conferences:
            if conf.series != lastseries:
                if currentgroup:
                    choices.append(_unwrap_addresses(currentgroup))
                currentgroup = [conf.series.name, set()]
                lastseries = conf.series
            currentgroup[1].add(conf.contactaddr)
            currentgroup[1].add(conf.sponsoraddr)
        if currentgroup:
            choices.append(_unwrap_addresses(currentgroup))
        self.fields['senderaddr'].choices = choices

    def prepare(self):
        if self.is_confirm:
            for f in self.fields:
                self.fields[f].widget.attrs['readonly'] = 'true'
                self.fields[f].widget.attrs['data-readonly'] = 1
            self.warning_text_below = 'Please confirm that you really want to send this email! There is no going back!'
            self.data['textpreview'] = self.textpreview.replace("\n", "<br/>")
            self.data['htmlpreview'] = self.htmlpreview
            self.fields['text'].widget = django.forms.widgets.HiddenInput()
            del self.fields['available_fields']
        else:
            del self.fields['textpreview']
            del self.fields['htmlpreview']
