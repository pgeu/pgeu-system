import django.forms
from django.conf import settings
from django.core.exceptions import ValidationError

from collections import OrderedDict

from postgresqleu.util.widgets import StaticTextWidget, EmailTextWidget
from postgresqleu.util.backendforms import BackendForm
from postgresqleu.util.backendlookups import GeneralAccountLookup
from postgresqleu.membership.models import Member, MemberLog, Meeting, MembershipConfiguration
from postgresqleu.membership.backendlookups import MemberLookup


class BackendConfigForm(BackendForm):
    helplink = 'membership'

    class Meta:
        model = MembershipConfiguration
        fields = ['sender_email', 'membership_years', 'membership_cost', 'country_validator',
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


class BackendMeetingForm(BackendForm):
    helplink = 'meetings'
    list_fields = ['name', 'dateandtime', ]

    class Meta:
        model = Meeting
        fields = ['name', 'dateandtime', 'allmembers', 'members', 'botname', ]

    selectize_multiple_fields = {
        'members': MemberLookup(),
    }


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
