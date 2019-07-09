from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from postgresqleu.util.forms import ConcurrentProtectedModelForm
from postgresqleu.util.widgets import EmailTextWidget, MonospaceTextarea

from postgresqleu.confreg.models import RegistrationType, ConferenceRegistration
from .models import Wikipage, Signup, AttendeeSignup


class WikipageEditForm(ConcurrentProtectedModelForm):
    class Meta:
        model = Wikipage
        fields = ('contents',)


class WikipageAdminEditForm(ConcurrentProtectedModelForm):
    selectize_multiple_fields = ['author', 'viewer_regtype', 'editor_regtype', 'viewer_attendee', 'editor_attendee']

    def __init__(self, *args, **kwargs):
        super(WikipageAdminEditForm, self).__init__(*args, **kwargs)
        self.fields['author'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
        self.fields['author'].label_from_instance = lambda r: "{0} <{1}>".format(r.fullname, r.email)
        self.fields['viewer_regtype'].queryset = RegistrationType.objects.filter(conference=self.instance.conference)
        self.fields['editor_regtype'].queryset = RegistrationType.objects.filter(conference=self.instance.conference)
        self.fields['viewer_attendee'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
        self.fields['viewer_attendee'].label_from_instance = lambda r: "{0} <{1}>".format(r.fullname, r.email)
        self.fields['editor_attendee'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
        self.fields['editor_attendee'].label_from_instance = lambda r: "{0} <{1}>".format(r.fullname, r.email)

    class Meta:
        model = Wikipage
        exclude = ['conference', ]
        widgets = {
            'contents': MonospaceTextarea,
        }


class SignupSubmitForm(forms.Form):
    choice = forms.ChoiceField(required=False, label='')

    def __init__(self, signup, attendee_signup, *args, **kwargs):
        self.signup = signup
        self.attendee_signup = attendee_signup
        super(SignupSubmitForm, self).__init__(*args, **kwargs)

        if signup.options:
            choices = signup.options.split(',')
            self.fields['choice'].choices = [(k, k) for k in choices]
            self.fields['choice'].choices.insert(0, ('', ''))
        else:
            # This one is boolean only
            self.fields['choice'].choices = (('', ''), ('yes', 'Yes'), ('', 'No'), )

        if attendee_signup:
            self.fields['choice'].initial = attendee_signup.choice

    def clean_choice(self):
        if self.cleaned_data.get('choice', '') and self.signup.maxsignups > 0:
            # Verify maximum uses.
            if self.signup.optionvalues:
                # We count maximum *value* in this case, not number of entries
                if self.attendee_signup:
                    qs = self.signup.attendeesignup_set.exclude(id=self.attendee_signup.id)
                else:
                    qs = self.signup.attendeesignup_set.all()
                optionstrings = self.signup.options.split(',')
                optionvalues = self.signup.optionvalues.split(',')
                currnum = sum([int(optionvalues[optionstrings.index(s.choice)]) for s in qs])
                addnum = int(optionvalues[optionstrings.index(self.cleaned_data.get('choice'))])
                if currnum + addnum > self.signup.maxsignups:
                    raise ValidationError("This signup is limited to {0} entries.".format(self.signup.maxsignups))
            else:
                if self.attendee_signup:
                    currnum = self.signup.attendeesignup_set.exclude(id=self.attendee_signup.id).count()
                else:
                    currnum = self.signup.attendeesignup_set.count()
                if currnum >= self.signup.maxsignups:
                    raise ValidationError("This signup is limited to {0} attendees.".format(self.signup.maxsignups))

        return self.cleaned_data['choice']


class SignupAdminEditForm(ConcurrentProtectedModelForm):
    selectize_multiple_fields = ['author', 'regtypes', 'attendees']

    def __init__(self, *args, **kwargs):
        super(SignupAdminEditForm, self).__init__(*args, **kwargs)
        self.fields['author'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
        self.fields['author'].label_from_instance = lambda r: "{0} <{1}>".format(r.fullname, r.email)
        self.fields['regtypes'].queryset = RegistrationType.objects.filter(conference=self.instance.conference)
        self.fields['attendees'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
        self.fields['attendees'].label_from_instance = lambda r: "{0} <{1}>".format(r.fullname, r.email)

    class Meta:
        model = Signup
        exclude = ['conference', ]


class SignupAdminEditSignupForm(ConcurrentProtectedModelForm):
    choice = forms.ChoiceField(required=True)

    class Meta:
        model = AttendeeSignup
        fields = ['attendee', 'choice', ]

    def __init__(self, signup, *args, **kwargs):
        self.signup = signup
        self.isnew = kwargs.pop('isnew')
        super(SignupAdminEditSignupForm, self).__init__(*args, **kwargs)

        if self.isnew:
            self.fields['attendee'].queryset = ConferenceRegistration.objects.filter(conference=signup.conference).filter(
                Q(user_attendees=signup) | Q(regtype__user_regtypes=signup)).exclude(attendeesignup__signup=signup).distinct()
        else:
            del self.fields['attendee']
            self.update_protected_fields()

        if signup.options:
            choices = signup.options.split(',')
            self.fields['choice'].choices = [(k, k) for k in choices]
            self.fields['choice'].choices.insert(0, ('', ''))
        else:
            # This one is boolean only
            self.fields['choice'].choices = (('', ''), ('yes', 'Yes'), ('', 'No'), )
            self.fields['choice'].required = False


class SignupSendmailForm(forms.Form):
    _recipient_choices = [
        ('*', '** Pick recipients of mail'),
        ('all', 'All recipieints'),
        ('responded', 'Recipients who have responded'),
        ('noresp', 'Recipients who have not responded'),
    ]

    subject = forms.CharField(max_length=100, required=True)
    body = forms.CharField(widget=EmailTextWidget, required=True)
    recipients = forms.ChoiceField(required=True)
    confirm = forms.BooleanField(required=True)

    def __init__(self, conference, additional_choices, *args, **kwargs):
        if 'num' in kwargs:
            self.num = kwargs['num']
            del kwargs['num']
        else:
            self.num = None

        r = super(SignupSendmailForm, self).__init__(*args, **kwargs)

        self.recipient_choices = self._recipient_choices + additional_choices
        self.fields['recipients'].choices = self.recipient_choices
        self.fields['subject'].help_text = "Subject will be prefixed with <b>[{0}]</b>".format(conference.conferencename)

        if 'data' in kwargs:
            # This is a re-post of the form.
            self.fields['confirm'].help_text = "Please confirm that you want to send this to {0} recipients".format(self.num)
        else:
            # First post of the form!
            del self.fields['confirm']

        return r

    def clean_recipients(self):
        if self.cleaned_data['recipients'] == '*':
            raise ValidationError("Pick a set of recipients for this mail!")
