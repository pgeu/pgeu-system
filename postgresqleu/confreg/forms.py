from django import forms
from django.forms import RadioSelect
from django.forms import ValidationError
from django.forms.utils import ErrorList
from django.contrib.auth.models import User
from django.utils.safestring import mark_safe
from django.utils.html import escape

from django.db.models.fields.files import ImageFieldFile

from models import Conference
from models import ConferenceRegistration, RegistrationType, Speaker
from models import ConferenceAdditionalOption, Track, RegistrationClass
from models import ConferenceSession, ConferenceSessionFeedback
from models import PrepaidVoucher, DiscountCode, AttendeeMail

from regtypes import validate_special_reg_type
from postgresqleu.util.magic import magicdb

from postgresqleu.countries.models import Country

from datetime import datetime, date, timedelta
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
        self.fields['regtype'].queryset = RegistrationType.objects.filter(conference=self.instance.conference).order_by('sortkey')
        self.fields['photoconsent'].required = True
        for f in self.instance.conference.remove_fields:
            del self.fields[f]

        if self.regforother:
            self.fields['email'].widget.attrs['readonly'] = True
        self.fields['additionaloptions'].queryset =    ConferenceAdditionalOption.objects.filter(
            conference=self.instance.conference, public=True)
        self.fields['country'].queryset = Country.objects.order_by('printable_name')

        if not self.regforother:
            self.intro_html = mark_safe(u'<p>You are currently making a registration for account<br/><i>{0} ({1} {2} &lt;{3}&gt;).</i></p>'.format(escape(self.user.username), escape(self.user.first_name), escape(self.user.last_name), escape(self.user.email)))
        else:
            self.intro_html = mark_safe(u'<p>You are currently editing a registration for somebody other than yourself.</p>')


    def clean_regtype(self):
        newval = self.cleaned_data.get('regtype')
        if self.instance and newval == self.instance.regtype:
            # Registration type not changed, so it's ok to save
            # (we don't want to prohibit other edits for somebody who has
            #  an already-made registration with an expired registration type)
            return newval

        if newval and not newval.active:
            raise forms.ValidationError('Registration type "%s" is currently not available.' % newval)

        if newval and newval.activeuntil and newval.activeuntil < datetime.today().date():
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
                    raise ValidationError(u'There is already a registration made with this email address, that is part of a multiple registration entry made by {0} {1} ({2}).'.format(
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
        if newval=='': return newval

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
                if c.validuntil and c.validuntil < date.today():
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
                    if not o in selected:
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
                current_count = option.conferenceregistration_set.count()
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

        if cleaned_data.has_key('vouchercode') and cleaned_data['vouchercode']:
            # We know it's there, and that it exists - but is it for the
            # correct type of registration?
            errs = []
            try:
                v = PrepaidVoucher.objects.get(vouchervalue=cleaned_data['vouchercode'],
                                               conference=self.instance.conference)
                if not cleaned_data.has_key('regtype'):
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

        if cleaned_data.has_key('regtype') and cleaned_data['regtype']:
            if cleaned_data['regtype'].requires_option.exists():
                regtype = cleaned_data['regtype']
                found = False
                if cleaned_data.has_key('additionaloptions') and cleaned_data['additionaloptions']:
                    for x in regtype.requires_option.all():
                        if x in cleaned_data['additionaloptions']:
                            found = True
                            break
                if not found:
                    self._errors['regtype'] = 'Registration type "%s" requires at least one of the following additional options to be picked: %s' % (regtype, ", ".join([x.name for x in regtype.requires_option.all()]))

        if cleaned_data.has_key('additionaloptions') and cleaned_data['additionaloptions'] and cleaned_data.has_key('regtype'):
            regtype = cleaned_data['regtype']
            errs = []
            for ao in cleaned_data['additionaloptions']:
                if ao.requires_regtype.exists():
                    if not regtype in ao.requires_regtype.all():
                        errs.append('Additional option "%s" requires one of the following registration types: %s.' % (ao.name, ", ".join(x.regtype for x in ao.requires_regtype.all())))
            if len(errs):
                self._errors['additionaloptions'] = self.error_class(errs)

        return cleaned_data

    class Meta:
        model = ConferenceRegistration
        exclude = ('conference','attendee','registrator','payconfirmedat','payconfirmedby','created', 'regtoken', )
        widgets = {
            'photoconsent': forms.Select(choices=((None, ''), (True, 'I consent to having my photo taken'), (False, "I don't want my photo taken"))),
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
            if conf.asktshirt: fields.append(self['shirtsize'])
            if conf.askfood: fields.append(self['dietary'])
            if conf.askshareemail: fields.append(self['shareemail'])
            yield {'id': 'conference_info',
                   'legend': 'Conference information',
                   'fields': fields}

        if self.instance.conference.askphotoconsent:
            yield {'id': 'consent_info',
                   'legend': 'Consent',
                   'fields': [self[x] for x in ['photoconsent', ]],
            }

        if conf.conferenceadditionaloption_set.filter(public=True).exists():
            yield {'id': 'additional_options',
                   'legend': 'Additional options',
                   'intro': conf.additionalintro,
                   'fields': [self['additionaloptions'],],
                   }

        yield { 'id': 'voucher_codes',
                'legend': 'Voucher codes',
                'intro': 'If you have a voucher or discount code, enter it in this field. If you do not have one, just leave the field empty.',
                'fields': [self['vouchercode'],],
                }

class RegistrationChangeForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(RegistrationChangeForm, self).__init__(*args, **kwargs)
        self.fields['photoconsent'].required = True
        for f in self.instance.conference.remove_fields:
            del self.fields[f]

    class Meta:
        model = ConferenceRegistration
        fields = ('shirtsize', 'dietary', 'twittername', 'nick', 'shareemail', 'photoconsent', )
        widgets = {
            'photoconsent': forms.Select(choices=((None, ''), (True, 'I consent to having my photo taken'), (False, "I don't want my photo taken"))),
        }


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

class ConferenceSessionFeedbackForm(forms.ModelForm):
    topic_importance = forms.ChoiceField(widget=RadioSelect,choices=rating_choices, label='Importance of the topic')
    content_quality = forms.ChoiceField(widget=RadioSelect,choices=rating_choices, label='Quality of the content')
    speaker_knowledge = forms.ChoiceField(widget=RadioSelect,choices=rating_choices, label='Speakers knowledge of the subject')
    speaker_quality = forms.ChoiceField(widget=RadioSelect,choices=rating_choices, label='Speakers presentation skills')

    class Meta:
        model = ConferenceSessionFeedback
        exclude = ('conference','attendee','session')


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
                                                                          choices=[(x,x) for x in q.textchoices.split(";")],
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
        exclude = ('user', 'speakertoken')

    def clean_photofile(self):
        if not self.cleaned_data['photofile']:
            return self.cleaned_data['photofile'] # If it's None...
        if isinstance(self.cleaned_data['photofile'], ImageFieldFile):
            return self.cleaned_data['photofile'] # If it's unchanged...

        img = None
        try:
            from PIL import ImageFile
            p = ImageFile.Parser()
            p.feed(self.cleaned_data['photofile'].read())
            p.close()
            img = p.image
        except Exception, e:
            raise ValidationError("Could not parse image: %s" % e)
        if img.format != 'JPEG':
            raise ValidationError("Only JPEG format images are accepted, not '%s'" % img.format)
        if img.size[0] > 128 or img.size[1] > 128:
            raise ValidationError("Maximum image size is 128x128")
        return self.cleaned_data['photofile']

    def clean_twittername(self):
        if not self.cleaned_data['twittername']:
            return self.cleaned_data['twittername']
        if not self.cleaned_data['twittername'][0] == '@':
            return "@%s" % self.cleaned_data['twittername']
        return self.cleaned_data['twittername']

    def clean_fullname(self):
        if not self.cleaned_data['fullname'].strip():
            raise ValidationError("Your full name must be given. This will be used both in the speaker profile and in communications with the conference organizers.")
        return self.cleaned_data['fullname']


class CallForPapersForm(forms.ModelForm):
    class Meta:
        model = ConferenceSession
        fields = ('title', 'abstract', 'skill_level', 'track', 'speaker', 'submissionnote')

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
        if 'data' in kwargs and u'speaker' in kwargs['data']:
            vals.extend([int(x) for x in kwargs['data'].getlist('speaker')])

        self.fields['speaker'].queryset = Speaker.objects.filter(pk__in=vals)
        self.fields['speaker'].label_from_instance = lambda x: u"{0} <{1}>".format(x.fullname, x.email)
        self.fields['speaker'].required = True
        self.fields['speaker'].help_text = "Type the beginning of a speakers email address to add more speakers"

        if not self.instance.conference.skill_levels:
            del self.fields['skill_level']

        if not self.instance.conference.track_set.filter(incfp=True).count() > 0:
            del self.fields['track']
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
        if not self.currentspeaker in self.cleaned_data.get('speaker'):
            raise ValidationError("You cannot remove yourself as a speaker!")
        return self.cleaned_data.get('speaker')


class SessionCopyField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return u"{0}: {1} ({2})".format(obj.conference, obj.title, obj.status_string)

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
        except:
            raise ValidationError("URL does not validate")
        return u

class SessionSlidesFileForm(forms.Form):
    f = forms.FileField(label='Upload', required=False)
    license = forms.BooleanField(label='License', required=False, help_text='I confirm that this this file may be redistributed by the conference website')

    def clean_f(self):
        if not self.cleaned_data.has_key('f') or not self.cleaned_data['f']:
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
    regtype = forms.ModelChoiceField(queryset=RegistrationType.objects.filter(id=-1))
    count = forms.IntegerField(min_value=1, max_value=100)
    buyer = forms.ModelChoiceField(queryset=User.objects.all().order_by('username'), help_text="Pick the user who bought the batch. If he/she does not have an account, pick your own userid")
    invoice = forms.BooleanField(help_text="Automatically create invoice template for these vouchers. Note that the vouchers are created immediately, not at payment time! Also note that only a template is created and has to be finalized!", required=False)
    confirm = forms.BooleanField(help_text="Confirm that the chosen registration type and count are correct (there is no undo past this point, the vouchers will be created!")

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        super(PrepaidCreateForm, self).__init__(*args, **kwargs)
        self.fields['regtype'].queryset=RegistrationType.objects.filter(conference=conference)
        self.fields['buyer'].label_from_instance=lambda x: u'{0} {1} <{2}> ({3})'.format(x.first_name, x.last_name, x.email, x.username)
        if not (self.data.has_key('regtype')
                and self.data.has_key('count')
                and self.data.get('regtype')
                and self.data.get('count')):
            del self.fields['confirm']

class EmailSendForm(forms.Form):
    ids = forms.CharField(label="List of id's", widget=forms.widgets.HiddenInput())
    returnurl = forms.CharField(label="Return url", widget=forms.widgets.HiddenInput())
    sender = forms.EmailField(label="Sending email")
    subject = forms.CharField(label="Subject", min_length=10)
    text = forms.CharField(label="Email text", min_length=50, widget=forms.Textarea)
    confirm = forms.BooleanField(help_text="Confirm that you really want to send this email! Double and triple check the text and sender!")

    def __init__(self, *args, **kwargs):
        super(EmailSendForm, self).__init__(*args, **kwargs)
        self.fields['ids'].widget.attrs['readonly'] = True
        readytogo = False
        if self.data and self.data.has_key('ids') and self.data.has_key('sender') and self.data.has_key('subject') and self.data.has_key('text'):
            if len(self.data['ids']) > 1 and len(self.data['sender']) > 5 and len(self.data['subject']) > 10 and len(self.data['text']) > 50:
                readytogo = True
        if not readytogo:
            del self.fields['confirm']

class EmailSessionForm(forms.Form):
    sender = forms.EmailField(label="Sending email")
    subject = forms.CharField(label="Subject", min_length=10)
    returnurl = forms.CharField(label="Return url", widget=forms.widgets.HiddenInput(), required=False)
    text = forms.CharField(label="Email text", min_length=50, widget=forms.Textarea)
    confirm = forms.BooleanField(help_text="Confirm that you really want to send this email! Double and triple check the text and sender!")

    def __init__(self, *args, **kwargs):
        super(EmailSessionForm, self).__init__(*args, **kwargs)
        readytogo = False
        if self.data and self.data.has_key('sender') and self.data.has_key('subject') and self.data.has_key('text'):
            if len(self.data['sender']) > 5 and len(self.data['subject']) > 10 and len(self.data['text']) > 50:
                readytogo = True
        if not readytogo:
            del self.fields['confirm']


class BulkRegistrationForm(forms.Form):
    recipient_name = forms.CharField(required=True, max_length=100,label='Invoice recipient name')
    recipient_address = forms.CharField(required=True, max_length=100, label='Invoice recipient address', widget=forms.Textarea)
    email_list = forms.CharField(required=True, label='Emails to pay for', widget=forms.Textarea)

    def clean_email_list(self):
        email_list = self.cleaned_data.get('email_list')
        emails = [e for e in email_list.splitlines(False) if e]
        if len(emails) < 2:
            raise ValidationError('Bulk payments can only be done for 2 or more emails')
        return email_list

class AttendeeMailForm(forms.ModelForm):
    confirm = forms.BooleanField(label="Confirm", required=False)
    class Meta:
        model = AttendeeMail
        exclude = ('conference', )

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        super(AttendeeMailForm, self).__init__(*args, **kwargs)

        self.fields['regclasses'].widget = forms.CheckboxSelectMultiple()
        self.fields['regclasses'].queryset = RegistrationClass.objects.filter(conference=self.conference)

        if not (self.data.get('regclasses') and self.data.get('subject') and self.data.get('message')):
            del self.fields['confirm']

    def clean_confirm(self):
        if not self.cleaned_data['confirm']:
            raise ValidationError("Please check this box to confirm that you are really sending this email! There is no going back!")


class WaitlistOfferForm(forms.Form):
    hours = forms.IntegerField(min_value=1, max_value=240, label='Offer valid for (hours)', initial=48)
    until = forms.DateTimeField(label='Offer valid until', initial=(datetime.now() + timedelta(hours=48)).strftime('%Y-%m-%d %H:%M'))
    confirm = forms.BooleanField(help_text='Confirm')

    def __init__(self, *args, **kwargs):
        super(WaitlistOfferForm, self).__init__(*args, **kwargs)
        if self.data:
            self.reg_list = self._get_id_list_from_data()
            if len(self.reg_list) == 1:
                self.fields['confirm'].help_text = "Confirm that you want to send an offer to an attendee on the waitlist"
            else:
                self.fields['confirm'].help_text = "Confirm that you want to send an offer to {0} attendees on the waitlist".format(len(self.reg_list))
            if self.data.get('submit') == 'Make offer for hours':
                del self.fields['until']
            else:
                del self.fields['hours']
        else:
            del self.fields['confirm']

    def _get_id_list_from_data(self):
        if not self.data: return []
        l = []
        for k,v in self.data.items():
            if v == '1' and k.startswith('reg_'):
                l.append(int(k[4:]))
        return l

    def clean(self):
        if len(self.reg_list)==0:
            raise ValidationError("At least one registration must be selected to make an offer")
        return self.cleaned_data

class WaitlistSendmailForm(forms.Form):
    TARGET_ALL=0
    TARGET_OFFERS=1
    TARGET_NOOFFERS=2

    TARGET_CHOICES = (
        (TARGET_ALL, 'All attendees on waitlist'),
        (TARGET_OFFERS, 'Only attendees with active offers'),
        (TARGET_NOOFFERS, 'Only attendees without active offers'),
    )

    POSITION_NONE=0
    POSITION_FULL=1
    POSITION_ONLY=2
    POSITION_SIZE=3
    POSITION_CHOICES = (
        (POSITION_NONE, 'No position information'),
        (POSITION_FULL, 'Both position and size of waitlist'),
        (POSITION_ONLY, 'Only position on waitlist'),
        (POSITION_SIZE, 'Only size of waitlist'),
    )

    waitlist_target = forms.ChoiceField(required=True, choices=TARGET_CHOICES)
    subject = forms.CharField(max_length=100, required=True)
    message = forms.CharField(required=True, widget=forms.Textarea)
    include_position = forms.ChoiceField(required=True, choices=POSITION_CHOICES,
                                         help_text="Include a footer with information about waitpost position and/or size")
    confirm = forms.BooleanField(help_text="Confirm that you are ready to send this email!", required=False)

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        super(WaitlistSendmailForm, self).__init__(*args, **kwargs)
        if not (self.data.get('subject') and self.data.get('message')):
            del self.fields['confirm']
        self.fields['subject'].help_text = u"Will be prefixed by [{0}]".format(conference.conferencename)

    def clean_confirm(self):
        if not self.cleaned_data['confirm']:
            raise ValidationError("Please check this box to confirm that you are really sending this email! There is no going back!")

class TransferRegForm(forms.Form):
    transfer_from = forms.ModelChoiceField(ConferenceRegistration.objects.filter(id=-1))
    transfer_to = forms.ModelChoiceField(ConferenceRegistration.objects.filter(id=-1))
    confirm = forms.BooleanField(help_text="Confirm that you want to transfer the registration with the given steps!", required=False)

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        super(TransferRegForm, self).__init__(*args, **kwargs)
        self.fields['transfer_from'].queryset = ConferenceRegistration.objects.filter(conference=conference, payconfirmedat__isnull=False)
        self.fields['transfer_to'].queryset = ConferenceRegistration.objects.filter(conference=conference, payconfirmedat__isnull=True)
        if not (self.data.has_key('transfer_from') and self.data.has_key('transfer_to')):
            del self.fields['confirm']
    def remove_confirm(self):
        del self.fields['confirm']


class CrossConferenceMailForm(forms.Form):
    senderaddr = forms.EmailField(min_length=5, required=True, label="Sender address")
    sendername = forms.CharField(min_length=5, required=True, label="Sender name")
    include = forms.CharField(widget=forms.widgets.HiddenInput(), required=False)
    exclude = forms.CharField(widget=forms.widgets.HiddenInput(), required=False)
    subject = forms.CharField(min_length=10, max_length=80, required=True)
    text = forms.CharField(min_length=30, required=True, widget=forms.Textarea)

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
