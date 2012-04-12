from django.contrib import admin
from django import forms
from django.forms import ValidationError
from django.db.models.fields.files import ImageFieldFile
from postgresqleu.confreg.models import *
from postgresqleu.confreg.dbimage import InlinePhotoWidget
from datetime import datetime

class ConferenceAdmin(admin.ModelAdmin):
	list_display = ('conferencename', 'startdate', 'enddate')
	ordering = ('-startdate', )
	filter_horizontal = ('administrators','testers','talkvoters',)

class ConferenceRegistrationForm(forms.ModelForm):
	class Meta:
		model = ConferenceRegistration

	def __init__(self, *args, **kwargs):
		super(ConferenceRegistrationForm, self).__init__(*args, **kwargs)
		if 'instance' in kwargs:
			self.fields['additionaloptions'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.instance.conference)


class ConferenceRegistrationAdmin(admin.ModelAdmin):
	form = ConferenceRegistrationForm
	list_display = ['email', 'conference', 'firstname', 'lastname', 'created', 'regtype', 'payconfirmedat', ]
	list_filter = ['conference', 'regtype', ]
	search_fields = ['email', 'firstname', 'lastname', ]
	ordering = ['-payconfirmedat', 'lastname', 'firstname', ]
	actions= ['approve_conferenceregistration', ]

	def queryset(self, request):
		qs = super(ConferenceRegistrationAdmin, self).queryset(request)
		if request.user.is_superuser:
			return qs
		else:
			return qs.filter(conference__administrators=request.user)

	def approve_conferenceregistration(self, request, queryset):
		rows = queryset.filter(payconfirmedat__isnull=True).update(payconfirmedat=datetime.today(), payconfirmedby=request.user.username)
		self.message_user(request, '%s registration(s) marked as confirmed.' % rows)
	approve_conferenceregistration.short_description = "Confirm payments for selected users"

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
			self.fields['tentativeroom'].queryset = Room.objects.filter(conference=self.instance.conference)
			self.fields['tentativescheduleslot'].queryset = ConferenceSessionScheduleSlot.objects.filter(conference=self.instance.conference)

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
	list_display = ['title', 'conference', 'speaker_list', 'status', 'starttime', 'track', 'initialsubmit', ]
	list_filter = ['conference', 'track', 'status', ]
	search_fields = ['title', ]
	filter_horizontal = ('speaker',)

	def queryset(self, request):
		qs = super(ConferenceSessionAdmin, self).queryset(request)
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
		return request.user.is_superuser

class ConferenceSessionScheduleSlotAdmin(admin.ModelAdmin):
	list_display = ['conference', 'starttime', 'endtime', ]
	list_filter = ['conference']
	ordering = ['starttime', ]

class RegistrationTypeAdmin(admin.ModelAdmin):
	list_display = ['conference', 'regtype', 'cost', 'sortkey', 'active']
	list_filter = ['conference',]
	ordering = ['conference','regtype']

class ConferenceAdditionalOptionAdmin(admin.ModelAdmin):
	list_display = ['conference', 'name', 'maxcount', 'cost']
	list_filter = ['conference', ]
	ordering = ['conference', 'name', ]

class SpeakerAdminForm(forms.ModelForm):
	class Meta:
		model = Speaker

	def clean_photofile(self):
		if not self.cleaned_data['photofile']:
			return self.cleaned_data['photofile'] # If it's None...
		if isinstance(self.cleaned_data['photofile'], ImageFieldFile):
			# Non-modified one
			return self.cleaned_data['photofile']
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

class SpeakerAdmin(admin.ModelAdmin):
	list_display = ['user', 'email', 'fullname', 'has_abstract', 'has_photo']
	ordering = ['fullname']
	form = SpeakerAdminForm

class SpeakerPhotoAdmin(admin.ModelAdmin):
	def formfield_for_dbfield(self, db_field, **kwargs):
		if db_field.name == 'photo':
			kwargs['widget'] = InlinePhotoWidget
		return super(SpeakerPhotoAdmin,self).formfield_for_dbfield(db_field,**kwargs)

class TrackAdmin(admin.ModelAdmin):
	list_filter = ['conference', ]

	class Meta:
		model = Track

class RoomAdmin(admin.ModelAdmin):
	list_filter = ['conference', ]

	class Meta:
		model = Room

class ConferenceFeedbackQuestionAdmin(admin.ModelAdmin):
	list_display = ['conference', 'sortkey', 'newfieldset', 'question',]
	list_filter = ['conference', ]

class PrepaidVoucherInline(admin.TabularInline):
	model = PrepaidVoucher
	readonly_fields = ['user', 'usedate' ]
	exclude = ['vouchervalue', 'conference', ]
	extra = 0
	can_delete = False

class PrepaidBatchAdmin(admin.ModelAdmin):
	list_display = ['id', 'conference', 'buyer' ]
	list_filter = ['conference', ]
	inlines = [PrepaidVoucherInline, ]

class PrepaidVoucherAdmin(admin.ModelAdmin):
	list_display = ['vouchervalue', 'conference', 'batch', 'user', 'usedate', ]
	list_filter = ['conference', ]


admin.site.register(Conference, ConferenceAdmin)
admin.site.register(RegistrationType, RegistrationTypeAdmin)
admin.site.register(ShirtSize)
admin.site.register(ConferenceRegistration, ConferenceRegistrationAdmin)
admin.site.register(PaymentOption)
admin.site.register(ConferenceSession, ConferenceSessionAdmin)
admin.site.register(ConferenceSessionFeedback, ConferenceSessionFeedbackAdmin)
admin.site.register(ConferenceSessionScheduleSlot, ConferenceSessionScheduleSlotAdmin)
admin.site.register(Track, TrackAdmin)
admin.site.register(Room, RoomAdmin)
admin.site.register(Speaker, SpeakerAdmin)
admin.site.register(Speaker_Photo, SpeakerPhotoAdmin)
admin.site.register(ConferenceAdditionalOption, ConferenceAdditionalOptionAdmin)
admin.site.register(ConferenceFeedbackQuestion, ConferenceFeedbackQuestionAdmin)
admin.site.register(ConferenceFeedbackAnswer)
admin.site.register(PrepaidBatch, PrepaidBatchAdmin)
admin.site.register(PrepaidVoucher, PrepaidVoucherAdmin)
