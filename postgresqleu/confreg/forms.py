from django import forms
from django.forms import RadioSelect
from django.forms import ValidationError
from django.forms.utils import ErrorList
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from django.utils.html import escape
from django.utils import timezone

from postgresqleu.confsponsor.models import ScannedAttendee
from .models import Conference
from .models import ConferenceRegistration, RegistrationType, Speaker
from .models import ConferenceAdditionalOption, Track, RegistrationClass
from .models import ConferenceSession, ConferenceSessionFeedback, ConferenceSessionTag
from .models import PrepaidVoucher, DiscountCode, AttendeeMail
from .models import PRIMARY_SPEAKER_PHOTO_RESOLUTION

from .regtypes import validate_special_reg_type
from .twitter import get_all_conference_social_media
from postgresqleu.util.fields import UserModelChoiceField
from postgresqleu.util.widgets import EmailTextWidget, MonospaceTextarea
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
        try:
            r = ConferenceRegistration.objects.get(email=e, conference=self.instance.conference)
            if r.id != self.instance.id:
                # A registration is already made with this email address. If this is made by somebody
                # else but for us, we can in some cases let them know who it is.
                if r.registrator != getattr(self.instance, 'registrator', None):
                    raise ValidationError('There is already a registration made with this email address, that is part of a multiple registration entry made by {0} {1} ({2}).'.format(
                        r.registrator.first_name,
                        r.registrator.last_name,
                        r.registrator.email))
                # Else give a generic error
                raise ValidationError('There is already a registration made with this email address')
        except ConferenceRegistration.DoesNotExist:
            pass
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

        if cleaned_data.get('additionaloptions', None) and 'regtype' in cleaned_data:
            regtype = cleaned_data['regtype']
            errs = []
            for ao in cleaned_data['additionaloptions']:
                if ao.requires_regtype.exists():
                    if regtype not in ao.requires_regtype.all():
                        errs.append('Additional option "%s" requires one of the following registration types: %s.' % (ao.name, ", ".join(x.regtype for x in ao.requires_regtype.all())))
            if len(errs):
                self._errors['additionaloptions'] = self.error_class(errs)

        return cleaned_data

    class Meta:
        model = ConferenceRegistration
        fields = ('regtype', 'firstname', 'lastname', 'email', 'company', 'address',
                  'country', 'phone', 'shirtsize', 'dietary', 'additionaloptions',
                  'twittername', 'nick', 'badgescan', 'shareemail', 'photoconsent', 'vouchercode',
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
    class Meta:
        model = Speaker
        fields = ('fullname', 'company', 'abstract', 'photo512')

    def __init__(self, *args, **kwargs):
        super(SpeakerProfileForm, self).__init__(*args, **kwargs)
        self.fields['photo512'].help_text = 'Photo will be rescaled to {}x{} pixels. We reserve the right to make minor edits to speaker photos if necessary'.format(*PRIMARY_SPEAKER_PHOTO_RESOLUTION)

        for classname, social, impl in sorted(get_all_conference_social_media(), key=lambda x: x[1]):
            self.fields['social_{}'.format(social)] = forms.CharField(label="{} name".format(social.title()), max_length=250, required=False)
            self.fields['social_{}'.format(social)].initial = self.instance.attributes.get('social', {}).get(social, '')

    def clean(self):
        cleaned_data = super().clean()

        for classname, social, impl in sorted(get_all_conference_social_media(), key=lambda x: x[1]):
            fn = 'social_{}'.format(social)
            if cleaned_data.get(fn, None):
                try:
                    cleaned_data[fn] = impl.clean_identifier_form_value(cleaned_data[fn])
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

        for classname, social, impl in sorted(get_all_conference_social_media(), key=lambda x: x[1]):
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

        self.fields['speaker'].queryset = Speaker.objects.defer('photo', 'photo512').filter(pk__in=vals)
        self.fields['speaker'].label_from_instance = lambda x: "{0} <{1}>".format(x.fullname, x.email)
        self.fields['speaker'].required = True
        self.fields['speaker'].help_text = "Type the beginning of a speakers email address to add more speakers"

        if not self.instance.conference.skill_levels:
            del self.fields['skill_level']

        if self.instance.conference.callforpaperstags:
            self.fields['tags'].queryset = ConferenceSessionTag.objects.filter(conference=self.instance.conference)
            self.fields['tags'].label_from_instance = lambda x: x.tag
            self.fields['tags'].required = False
        else:
            del self.fields['tags']

        if not self.instance.conference.callforpapersrecording:
            del self.fields['recordingconsent']
        else:
            self.fields['recordingconsent'].help_text = "I give my consent for the conference organisers to record my presentation and give permission for them to distribute the recording under the license of their choice."

        if not self.instance.conference.track_set.filter(incfp=True).count() > 0:
            del self.fields['track']
        else:
            # Special case -- if a track already picked is no longer flagged as "incfp", it means that this particular
            # track has been closed. But we want to still allow editing of *other* details, so juste create a set
            # of tracks that includes just this one.
            if self.instance.track and not self.instance.track.incfp:
                self.fields['track'].queryset = Track.objects.filter(conference=self.instance.conference, pk=self.instance.track.pk)
                self.fields['track'].empty_label = None
            else:
                self.fields['track'].queryset = Track.objects.filter(conference=self.instance.conference, incfp=True).order_by('trackname')

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
        return self.cleaned_data.get('speaker')


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
        mtype = magicdb.buffer(f.read())
        if not mtype.startswith('application/pdf'):
            raise ValidationError("Uploaded files must be mime type PDF only, not %s" % mtype)
        f.seek(0)
        if not f.name.endswith('.pdf'):
            raise ValidationError("Uploaded files must have a filename ending in PDF")
        return f

    def clean(self):
        cleaned_data = super(SessionSlidesFileForm, self).clean()
        if cleaned_data.get('f', None) and not cleaned_data['license']:
            self.add_error('license', 'You must accept the license')
        return cleaned_data


class PrepaidCreateForm(forms.Form):
    regtype = forms.ModelChoiceField(label="Registration type", queryset=RegistrationType.objects.filter(id=-1))
    count = forms.IntegerField(label="Number of vouchers", min_value=1, max_value=100)
    buyer = forms.ModelChoiceField(queryset=User.objects.all().order_by('username'), help_text="Pick the user who bought the batch. If he/she does not have an account, pick your own userid")
    invoice = forms.BooleanField(help_text="Automatically create invoice for these vouchers and send it to the person ordering them.", required=False)
    invoiceaddress = forms.CharField(label="Invoice address", help_text="Complete address to put on invoice. Note that the name of the buyer is prepended to this!", required=False, widget=MonospaceTextarea)
    confirm = forms.BooleanField(help_text="Confirm that the chosen registration type and count are correct (there is no undo past this point, the vouchers will be created!")

    selectize_multiple_fields = {
        'buyer': GeneralAccountLookup(),
    }

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        super(PrepaidCreateForm, self).__init__(*args, **kwargs)
        self.fields['regtype'].queryset = RegistrationType.objects.filter(conference=conference)
        self.fields['buyer'].label_from_instance = lambda x: '{0} {1} <{2}> ({3})'.format(x.first_name, x.last_name, x.email, x.username)
        if not ('regtype' in self.data and
                'count' in self.data and
                'regtype' in self.data and
                self.data.get('count')):
            del self.fields['confirm']
        if 'invoice' in self.data and not self.data.get('invoiceaddress', ''):
            del self.fields['confirm']

    def clean(self):
        cleaned_data = super(PrepaidCreateForm, self).clean()
        if self.cleaned_data.get('invoice', False):
            if not self.cleaned_data.get('invoiceaddress'):
                self.add_error('invoiceaddress', 'Invoice address must be specified if invoice creation is selected!')
        return cleaned_data


class AttendeeMailForm(forms.ModelForm):
    confirm = forms.BooleanField(label="Confirm", required=False)

    class Meta:
        model = AttendeeMail
        fields = ('regclasses', 'addopts', 'tovolunteers', 'tocheckin', 'subject', 'message')
        widgets = {
            'message': EmailTextWidget,
        }

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

        self.fields['regclasses'].widget = forms.CheckboxSelectMultiple()
        self.fields['regclasses'].queryset = RegistrationClass.objects.filter(conference=self.conference)
        self.fields['regclasses'].label_from_instance = self.regclass_label

        self.fields['addopts'].widget = forms.CheckboxSelectMultiple()
        self.fields['addopts'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.conference)
        self.fields['addopts'].label_from_instance = self.addopts_label

        self.fields['subject'].help_text = 'Subject will be prefixed with <strong>[{}]</strong>'.format(conference)

        if not (self.data.get('subject') and self.data.get('message')):
            del self.fields['confirm']

    def clean_confirm(self):
        if not self.cleaned_data['confirm']:
            raise ValidationError("Please check this box to confirm that you are really sending this email! There is no going back!")


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

    POSITION_NONE = 0
    POSITION_FULL = 1
    POSITION_ONLY = 2
    POSITION_SIZE = 3
    POSITION_CHOICES = (
        (POSITION_NONE, 'No position information'),
        (POSITION_FULL, 'Both position and size of waitlist'),
        (POSITION_ONLY, 'Only position on waitlist'),
        (POSITION_SIZE, 'Only size of waitlist'),
    )

    waitlist_target = forms.ChoiceField(required=True, choices=TARGET_CHOICES)
    subject = forms.CharField(max_length=100, required=True)
    message = forms.CharField(required=True, widget=EmailTextWidget)
    include_position = forms.ChoiceField(required=True, choices=POSITION_CHOICES,
                                         help_text="Include a footer with information about waitpost position and/or size")
    confirm = forms.BooleanField(help_text="Confirm that you are ready to send this email!", required=False)

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        super(WaitlistSendmailForm, self).__init__(*args, **kwargs)
        if not (self.data.get('subject') and self.data.get('message')):
            del self.fields['confirm']
        self.fields['subject'].help_text = "Will be prefixed by [{0}]".format(conference.conferencename)

    def clean_confirm(self):
        if not self.cleaned_data['confirm']:
            raise ValidationError("Please check this box to confirm that you are really sending this email! There is no going back!")


class TransferRegForm(forms.Form):
    transfer_from = forms.ModelChoiceField(ConferenceRegistration.objects.filter(id=-1))
    transfer_to = forms.ModelChoiceField(ConferenceRegistration.objects.filter(id=-1))
    create_invoice = forms.BooleanField(required=False, help_text="Create an invoice for this transfer, and perform the transfer only once the invoice is paid?")
    invoice_recipient = UserModelChoiceField(User.objects.all(), required=False, label="Invoice recipient user", help_text="Not required but if specified it will attach the invoice to this account so it can be viewed in the users inovice list")
    invoice_name = forms.CharField(required=False, label="Invoice recipient name", help_text="Name of the recipient of the invoice")
    invoice_email = forms.EmailField(required=False, label="Invoice recipient email", help_text="E-mail to send the invoice to")
    invoice_address = forms.CharField(widget=MonospaceTextarea, required=False)
    confirm = forms.BooleanField(help_text="Confirm that you want to transfer the registration with the given steps!", required=False)

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        super(TransferRegForm, self).__init__(*args, **kwargs)
        self.fields['transfer_from'].queryset = ConferenceRegistration.objects.filter(conference=conference, payconfirmedat__isnull=False, canceledat__isnull=True, transfer_from_reg__isnull=True)
        self.fields['transfer_to'].queryset = ConferenceRegistration.objects.filter(conference=conference, payconfirmedat__isnull=True, canceledat__isnull=True, bulkpayment__isnull=True)
        if not ('transfer_from' in self.data and 'transfer_to' in self.data):
            del self.fields['confirm']
        if not conference.transfer_cost:
            del self.fields['create_invoice']
            del self.fields['invoice_recipient']
            del self.fields['invoice_name']
            del self.fields['invoice_email']
            del self.fields['invoice_address']

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
    senderaddr = forms.EmailField(min_length=5, required=True, label="Sender address")
    sendername = forms.CharField(min_length=5, required=True, label="Sender name")
    include = forms.CharField(widget=forms.widgets.HiddenInput(), required=False)
    exclude = forms.CharField(widget=forms.widgets.HiddenInput(), required=False)
    subject = forms.CharField(min_length=10, max_length=80, required=True)
    text = forms.CharField(min_length=30, required=True, widget=EmailTextWidget)

    confirm = forms.BooleanField(label="Confirm", required=False)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(CrossConferenceMailForm, self).__init__(*args, **kwargs)

        if not self.user.is_superuser:
            conferences = list(Conference.objects.filter(series__administrators=self.user))
            self.fields['senderaddr'] = forms.ChoiceField(label="Sender address", choices=set(
                                                          [(c.contactaddr, c.contactaddr) for c in conferences] +
                                                          [(c.sponsoraddr, c.sponsoraddr) for c in conferences]))

        if not (self.data.get('senderaddr') and self.data.get('sendername') and self.data.get('subject') and self.data.get('text')):
            self.remove_confirm()

    def clean_confirm(self):
        if not self.cleaned_data['confirm']:
            raise ValidationError("Please check this box to confirm that you are really sending this email! There is no going back!")

    def remove_confirm(self):
        if 'confirm' in self.fields:
            del self.fields['confirm']
