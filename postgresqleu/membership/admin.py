from django.contrib import admin
from django.db.models import Q
from django.http import HttpResponseRedirect

from datetime import datetime
import urllib

from models import Member, MemberLog, Meeting


class ActiveMemberFilter(admin.SimpleListFilter):
    title = 'Active'
    parameter_name = 'isactive'

    def lookups(self, request, model_admin):
        return (
            ('Yes', 'Yes'),
            ('No', 'No'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'Yes':
            return queryset.filter(paiduntil__gte=datetime.now())
        if self.value() == 'No':
            return queryset.filter(Q(paiduntil__lt=datetime.now()) | Q(paiduntil__isnull=True))
        return queryset


class MemberAdmin(admin.ModelAdmin):
    list_display = ('user', 'fullname', 'country', 'membersince', 'paiduntil', )
    ordering = ('user',)
    list_filter = (ActiveMemberFilter, )
    actions = ['email_members', ]

    def change_view(self, request, object_id, extra_context=None):
        member = Member(pk=object_id)
        return super(MemberAdmin, self).change_view(request, object_id, extra_context={
            'logentries': member.memberlog_set.all().order_by('-timestamp')[:10],
        })

    def email_members(self, request, queryset):
        selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
        return HttpResponseRedirect('/admin/django/membership/_email/?ids=%s&orig=%s' % (','.join(selected), urllib.quote(urllib.urlencode(request.GET))))
    email_members.short_description = 'Send email to selected members'


class MemberLogAdmin(admin.ModelAdmin):
    list_display = ('member', 'timestamp', 'message', )
    ordering = ('-timestamp', )


class MeetingAdmin(admin.ModelAdmin):
    list_display = ('name', 'dateandtime', )
    filter_horizontal = ('members', )


admin.site.register(Member, MemberAdmin)
admin.site.register(MemberLog, MemberLogAdmin)
admin.site.register(Meeting, MeetingAdmin)
