from django.contrib import admin
from django import forms
from django.forms import ValidationError

from datetime import datetime

from models import *

class MemberAdmin(admin.ModelAdmin):
	list_display = ('user', 'fullname', 'country', 'membersince', 'paiduntil', )
	ordering = ('user',)

class MemberLogAdmin(admin.ModelAdmin):
	list_display = ('member', 'timestamp', 'message', )
	ordering = ('-timestamp', )

admin.site.register(Member, MemberAdmin)
admin.site.register(MemberLog, MemberLogAdmin)
