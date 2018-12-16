import django.forms

from collections import OrderedDict

from postgresqleu.util.backendforms import BackendForm
from postgresqleu.util.backendlookups import GeneralAccountLookup
from postgresqleu.membership.models import Member, MemberLog, Meeting
from postgresqleu.membership.backendlookups import MemberLookup


class MemberLogManager(object):
    title = "Log"
    singular = "log"
    can_add = False

    def get_list(self, instance):
        return [(None, l.timestamp, l.message) for l in MemberLog.objects.filter(member=instance).order_by('-timestamp')]


class BackendMemberForm(BackendForm):
    list_fields = ['fullname', 'user', 'paiduntil']
    defaultsort = [[2, 'desc']]

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


class BackendMeetingForm(BackendForm):
    list_fields = ['name', 'dateandtime', ]

    class Meta:
        model = Meeting
        fields = ['name', 'dateandtime', 'allmembers', 'members', 'botname', ]

    selectize_multiple_fields = {
        'members': MemberLookup(),
    }
