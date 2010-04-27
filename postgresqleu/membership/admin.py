from django.contrib import admin
from django import forms
from django.forms import ValidationError

from datetime import datetime

from models import *

class MemberAdmin(admin.ModelAdmin):
	list_display = ('user', 'fullname', 'country', 'membersince', 'paiduntil', )
	ordering = ('user',)

	def change_view(self, request, object_id, extra_context=None):
		member = Member(pk=object_id)
		return super(MemberAdmin, self).change_view(request, object_id, extra_context={
				'logentries': member.memberlog_set.all().order_by('-timestamp')[:10],
				})

class MemberLogAdmin(admin.ModelAdmin):
	list_display = ('member', 'timestamp', 'message', )
	ordering = ('-timestamp', )

admin.site.register(Member, MemberAdmin)
admin.site.register(MemberLog, MemberLogAdmin)
