import django.forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from collections import OrderedDict
from datetime import timedelta

from postgresqleu.util.time import time_sinceoruntil, datetime_string
from postgresqleu.util.widgets import StaticTextWidget, EmailTextWidget
from postgresqleu.util.backendforms import BackendForm
from postgresqleu.membership.models import Member, MemberLog, Meeting, MembershipConfiguration
from postgresqleu.membership.models import MeetingType, MeetingReminder
from postgresqleu.membership.backendlookups import MemberLookup


class BackendConfigForm(BackendForm):
    helplink = 'membership'

    class Meta:
        model = MembershipConfiguration
        fields = ['sender_email', 'sender_name', 'membership_years', 'membership_cost', 'country_validator',
                  'paymentmethods', ]
        widgets = {
            'paymentmethods': django.forms.CheckboxSelectMultiple,
        }

    def fix_fields(self):
        self.fields['paymentmethods'].label_from_instance = lambda x: "{0}{1}".format(x.internaldescription, x.active and " " or " (INACTIVE)")
        self.fields['membership_cost'].help_text = "Membership cost in {0}".format(settings.CURRENCY_SYMBOL)


class MemberLogManager(object):
    title = "Log"
    singular = "log"
    can_add = False

    def get_list(self, instance):
        return [(None, l.timestamp, l.message) for l in MemberLog.objects.filter(member=instance).order_by('-timestamp')]


class BackendMemberForm(BackendForm):
    helplink = 'membership'
    list_fields = ['fullname', 'user', 'paiduntil']
    queryset_select_related = ['user', ]
    defaultsort = [['paiduntil', 'desc'], ['fullname', 'asc']]
    allow_email = True

    class Meta:
        model = Member
        fields = ['fullname', 'country', 'listed', 'country_exception',
                  'membersince', 'paiduntil', 'expiry_warning_sent', ]

    fieldsets = [
        {'id': 'user_info', 'Legend': 'User information', 'fields': ['fullname', 'country', 'listed', ]},
        {'id': 'admin_info', 'Legend': 'Administrative', 'fields': ['country_exception', ]},
        {'id': 'date_info', 'Legend': 'Date info', 'fields': ['membersince', 'paiduntil', 'expiry_warning_sent', ]},
    ]
    readonly_fields = ['membersince', 'paiduntil', 'expiry_warning_sent', ]

    linked_objects = OrderedDict({
        'log': MemberLogManager(),
    })

    @classmethod
    def get_column_filters(cls, conference):
        return {
            'Paid until': [],  # Empty list triggers the option to choose empty/not empty
        }


class BackendMeetingReminderForm(BackendForm):
    helplink = 'meetings'
    list_fields = ['sendat', 'sentat', ]
    readonly_fields = ['sentat', ]

    class Meta:
        model = MeetingReminder
        fields = ['sendat', 'sentat', ]

    def clean_sendat(self):
        if self.cleaned_data.get('sendat', None):
            print("FOO: %s" % self.cleaned_data.get('sendat', None))
            print("FOO2: %s" % self.instance.meeting.dateandtime)
            if self.cleaned_data.get('sendat') > self.instance.meeting.dateandtime - timedelta(minutes=30):
                raise ValidationError("Reminder must be set at least 30 minutes before the meeting starts!")
            if self.cleaned_data.get('sendat') < timezone.now():
                raise ValidationError("This timestamp is in the past!")
        else:
            print("BAR")
        return self.cleaned_data.get('sendat', None)

    def clean(self):
        d = super().clean()
        if self.instance.sentat:
            raise ValidationError("Cannot edit a reminder that has already been sent")
        return d


class MeetingReminderManager(object):
    title = 'Reminders'
    singular = 'Reminder'
    can_add = True

    def get_list(self, instance):
        return [
            (r.id, "{} ({})".format(datetime_string(r.sendat),
                                    time_sinceoruntil(r.sendat)),
             r.sentat is not None
            ) for r in MeetingReminder.objects.filter(meeting=instance)]

    def get_form(self, obj, POST):
        return BackendMeetingReminderForm

    def get_object(self, masterobj, subid):
        return MeetingReminder.objects.get(meeting=masterobj, pk=subid)

    def get_instancemaker(self, masterobj):
        return lambda: MeetingReminder(meeting=masterobj)


class BackendMeetingForm(BackendForm):
    helplink = 'meetings'
    list_fields = ['name', 'dateandtime', 'meetingtype', 'state']
    linked_objects = OrderedDict({
        'reminders': MeetingReminderManager(),
    })
    extrabuttons = [
        ('View meeting log', 'log/'),
        ('View attendees', 'attendees/'),
    ]

    class Meta:
        model = Meeting
        fields = ['name', 'dateandtime', 'allmembers', 'members', 'meetingtype', 'meetingadmins', 'botname', ]

    fieldsets = [
        {'id': 'meeting_info', 'legend': 'Meeting information', 'fields': ['name', 'dateandtime', 'allmembers', 'members']},
        {'id': 'meeting_impl', 'legend': 'Meeting implementation', 'fields': ['meetingtype', 'meetingadmins', 'botname']},
    ]

    selectize_multiple_fields = {
        'members': MemberLookup(),
        'meetingadmins': MemberLookup(),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove extra buttons unless we're in a web meeting and this web meeting has started
        if self.instance:
            if self.instance.meetingtype != MeetingType.WEB or self.instance.state == 0:
                self.extrabuttons = []
        else:
            self.extrabuttons = []

    def clean(self):
        d = super().clean()
        if d.get('meetingtype', None) == MeetingType.WEB:
            if d['botname']:
                self.add_error('botname', 'Bot name should not be specified for web meetings')
            if not d['meetingadmins']:
                self.add_error('meetingadmins', 'Meeting administrator(s) must be specified for web meetings')
        elif d.get('meetingtype', None) == MeetingType.IRC:
            if not d['botname']:
                self.add_error('botname', 'Bot name must be specified for IRC meetings')
            if d['meetingadmins']:
                self.add_error('meetingadmins', 'Meeting administrator(s) cannot be specified for IRC meetings')
        return d

    def clean_meetingtype(self):
        if self.cleaned_data.get('meetingtype', None) == MeetingType.WEB and not settings.MEETINGS_WS_BASE_URL:
            raise ValidationError("Web meetings server is not configured in local_settings.py")

        if self.instance and self.instance.state > 0 and self.instance.meetingtype != self.cleaned_data['meetingtype']:
            raise ValidationError("Cannot change the type of a meeting that has already started")

        return self.cleaned_data.get('meetingtype', None)


class BackendMemberSendEmailForm(django.forms.Form):
    helplink = 'membership'
    _from = django.forms.CharField(max_length=128, disabled=True, label="From")
    subject = django.forms.CharField(max_length=128, required=True)
    recipients = django.forms.Field(widget=StaticTextWidget, required=False)
    message = django.forms.CharField(widget=EmailTextWidget, required=True)
    idlist = django.forms.CharField(widget=django.forms.HiddenInput, required=True)
    confirm = django.forms.BooleanField(label="Confirm", required=False)

    def __init__(self, *args, **kwargs):
        super(BackendMemberSendEmailForm, self).__init__(*args, **kwargs)
        if not (self.data.get('subject') and self.data.get('message')):
            del self.fields['confirm']

    def clean_confirm(self):
        if not self.cleaned_data['confirm']:
            raise ValidationError("Please check this box to confirm that you are really sending this email! There is no going back!")
