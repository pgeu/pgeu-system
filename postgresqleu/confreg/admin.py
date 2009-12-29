from django.contrib import admin
from django import forms
from django.forms import ValidationError
from postgresqleu.confreg.models import *

class ConferenceRegistrationAdmin(admin.ModelAdmin):
	list_display = ['email', 'conference', 'firstname', 'lastname', 'created', 'regtype', 'payconfirmedat', ]
	list_filter = ['conference', 'regtype', ]
	search_fields = ['email', 'firstname', 'lastname', ]
	ordering = ['-payconfirmedat', 'lastname', 'firstname', ]

	def queryset(self, request):
		qs = super(ConferenceRegistrationAdmin, self).queryset(request)
		if request.user.is_superuser:
			return qs
		else:
			return qs.filter(conference__administrators=request.user)

	def has_change_permission(self, request, obj=None):
		if not obj:
			return True # So they can see the change list page
		if request.user.is_superuser:
			return True
		else:
			if obj.conference.administrators.filter(pk=request.user.id):
				return True
			else:
				return False
	has_delete_permission = has_change_permission

	def has_add_permission(self, request):
		if request.user.is_superuser:
			return True
		else:
			return False

class ConferenceSessionFeedbackAdmin(admin.ModelAdmin):
	ordering = ['session']
	list_display = ['conference', 'session', 'attendee', ]
	list_filter = ['conference', ]
	search_fields = ['session__title', ]

class ConferenceSessionForm(forms.ModelForm):
	class Meta:
		model = ConferenceSession

	def __init__(self, *args, **kwargs):
		super(ConferenceSessionForm, self).__init__(*args, **kwargs)
		if 'instance' in kwargs:
			self.fields['track'].queryset = Track.objects.filter(conference=self.instance.conference)
			self.fields['room'].queryset = Room.objects.filter(conference=self.instance.conference)

	def clean_track(self):
		if not self.cleaned_data['track']: return None
		if self.cleaned_data['track'].conference != self.cleaned_data['conference']:
			raise ValidationError("This track does not belong to this conference!")
		return self.cleaned_data['track']

	def clean_room(self):
		if not self.cleaned_data['room']: return None
		if self.cleaned_data['room'].conference != self.cleaned_data['conference']:
			raise ValidationError("This room does not belong to this conference!")
		return self.cleaned_data['room']

class ConferenceSessionAdmin(admin.ModelAdmin):
	form = ConferenceSessionForm
	list_display = ['conference', 'speaker', 'title', 'starttime', 'endtime', 'track', ]
	list_filter = ['conference', 'track', ]
	search_fields = ['title', ]

class RegistrationTypeAdmin(admin.ModelAdmin):
	list_display = ['conference', 'regtype', 'cost', 'active']
	list_filter = ['conference',]
	ordering = ['conference','regtype']

admin.site.register(Conference)
admin.site.register(RegistrationType, RegistrationTypeAdmin)
admin.site.register(ShirtSize)
admin.site.register(ConferenceRegistration, ConferenceRegistrationAdmin)
admin.site.register(PaymentOption)
admin.site.register(ConferenceSession, ConferenceSessionAdmin)
admin.site.register(ConferenceSessionFeedback, ConferenceSessionFeedbackAdmin)
admin.site.register(Track)
admin.site.register(Room)
admin.site.register(Speaker)
