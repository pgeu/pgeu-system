from django.contrib import admin
from django import forms
from django.http import HttpResponseRedirect
from django.forms import ValidationError
from django.db.models.fields.files import ImageFieldFile
from django.db.models import Count
from django.core import urlresolvers
from django.utils.safestring import mark_safe

from models import Conference, ConferenceRegistration, RegistrationType, Speaker
from models import ConferenceSession, Track, Room, ConferenceSessionScheduleSlot
from models import RegistrationClass, RegistrationDay
from models import ShirtSize, PaymentOption, ConferenceAdditionalOption
from models import ConferenceSessionFeedback, ConferenceFeedbackQuestion
from models import ConferenceFeedbackAnswer, Speaker_Photo
from models import PrepaidVoucher, PrepaidBatch, BulkPayment

from postgresqleu.confreg.dbimage import InlinePhotoWidget
from postgresqleu.accounting.models import Object

from datetime import datetime
import urllib

class ConferenceAdminForm(forms.ModelForm):
	class Meta:
		model = Conference
	accounting_object = forms.ChoiceField(choices=[], required=False)

	def __init__(self, *args, **kwargs):
		super(ConferenceAdminForm, self).__init__(*args, **kwargs)
		self.fields['accounting_object'].choices = [('', '----'),] + [(o.name, o.name) for o in Object.objects.filter(active=True)]

class ConferenceAdmin(admin.ModelAdmin):
	form = ConferenceAdminForm
	list_display = ('conferencename', 'active', 'startdate', 'enddate')
	ordering = ('-startdate', )
	filter_horizontal = ('administrators','testers','talkvoters',)

class ConferenceRegistrationForm(forms.ModelForm):
	class Meta:
		model = ConferenceRegistration

	def __init__(self, *args, **kwargs):
		super(ConferenceRegistrationForm, self).__init__(*args, **kwargs)
		if 'instance' in kwargs:
			self.fields['additionaloptions'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.instance.conference)
			self.fields['regtype'].queryset = RegistrationType.objects.filter(conference=self.instance.conference)


class ConferenceRegistrationAdmin(admin.ModelAdmin):
	form = ConferenceRegistrationForm
	list_display = ['email', 'conference', 'firstname', 'lastname', 'created_short', 'short_regtype', 'payconfirmedat_short', 'has_invoice', 'addoptions']
	list_filter = ['conference', 'regtype', 'additionaloptions', ]
	search_fields = ['email', 'firstname', 'lastname', ]
	ordering = ['-payconfirmedat', '-created', 'lastname', 'firstname', ]
	actions= ['approve_conferenceregistration', 'email_recipients']
	filter_horizontal = ('additionaloptions',)
	exclude = ('invoice','bulkpayment',)
	readonly_fields = ('invoice_link','bulkpayment_link',)

	def queryset(self, request):
		qs = super(ConferenceRegistrationAdmin, self).queryset(request)
		# If this is a POST, it's something that can modify data, and we
		# must not include the annotation there, since it causes the
		# django ORM to break. We only want it on the GET, which returns
		# the list that we render.
		if request.method != 'POST':
			qs = qs.annotate(addoptcount=Count('additionaloptions'))

		if request.user.is_superuser:
			return qs
		else:
			return qs.filter(conference__administrators=request.user)

	def addoptions(self, inst):
		return inst.addoptcount
	addoptions.short_description="Options"

	def payconfirmedat_short(self, inst):
		return inst.payconfirmedat
	payconfirmedat_short.short_description="Pay conf"

	def created_short(self, inst):
		return "<nobr>%s</nobr>" % inst.created.strftime("%Y-%m-%d %H:%M")
	created_short.allow_tags=True
	created_short.short_description="Created"

	def invoice_link(self, inst):
		if inst.invoice:
			url = urlresolvers.reverse('admin:invoices_invoice_change', args=(inst.invoice.id,))
			return mark_safe('<a href="%s">%s</a>' % (url, inst.invoice))
		else:
			return ""
	invoice_link.short_description = 'Invoice'

	def bulkpayment_link(self, inst):
		if inst.bulkpayment:
			url = urlresolvers.reverse('admin:confreg_bulkpayment_change', args=(inst.bulkpayment.id,))
			return mark_safe('<a href="%s">%s</a>' % (url, inst.bulkpayment))
		else:
			return ""
	bulkpayment_link.short_description = 'Bulk payment'

	def approve_conferenceregistration(self, request, queryset):
		rows = queryset.filter(payconfirmedat__isnull=True).update(payconfirmedat=datetime.today(), payconfirmedby=request.user.username)
		self.message_user(request, '%s registration(s) marked as confirmed.' % rows)
	approve_conferenceregistration.short_description = "Confirm payments for selected users"

	def email_recipients(self, request, queryset):
		selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
		return HttpResponseRedirect('/admin/confreg/_email/?ids=%s&orig=%s' % (','.join(selected), urllib.quote(urllib.urlencode(request.GET))))
	email_recipients.short_description = "Send email to selected users"

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
	actions= ['email_recipients', ]

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

	def email_recipients(self, request, queryset):
		selected = request.POST.getlist(admin.ACTION_CHECKBOX_NAME)
		return HttpResponseRedirect('/admin/confreg/_email_session_speaker/%s/?orig=%s' % (','.join(selected), urllib.quote(urllib.urlencode(request.GET))))
	email_recipients.short_description = "Send email to speakers of selected sessions"

class ConferenceSessionScheduleSlotAdmin(admin.ModelAdmin):
	list_display = ['conference', 'starttime', 'endtime', ]
	list_filter = ['conference']
	ordering = ['starttime', ]

class RegistrationClassAdmin(admin.ModelAdmin):
	list_display = ['regclass', 'conference', ]
	list_filter = ['conference',]
	ordering = ['conference','regclass']

class RegistrationDayAdmin(admin.ModelAdmin):
	list_display = ['day', 'conference', ]
	list_filter = ['conference', ]
	ordering = ['conference', 'day', ]

class RegistrationTypeAdminForm(forms.ModelForm):
	class Meta:
		model = RegistrationType

	def __init__(self, *args, **kwargs):
		super(RegistrationTypeAdminForm, self).__init__(*args, **kwargs)
		try:
			self.fields['regclass'].queryset = RegistrationClass.objects.filter(conference=self.instance.conference)
			self.fields['days'].queryset = RegistrationDay.objects.filter(conference=self.instance.conference)
		except Conference.DoesNotExist:
			# If we don't have a conference yet, we can just ignore the fact
			# that we couldn't list it.
			pass

class RegistrationTypeAdmin(admin.ModelAdmin):
	list_display = ['conference', 'regtype', 'cost', 'sortkey', 'active']
	list_filter = ['conference',]
	ordering = ['conference','regtype']
	form = RegistrationTypeAdminForm

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
	list_display = ['conference', 'trackname', 'sortkey', 'color', ]

	class Meta:
		model = Track

class RoomAdmin(admin.ModelAdmin):
	list_filter = ['conference', ]

	class Meta:
		model = Room

class ConferenceFeedbackQuestionAdmin(admin.ModelAdmin):
	list_display = ['conference', 'sortkey', 'newfieldset', 'question',]
	list_filter = ['conference', ]

class ConferenceFeedbackAnswerAdmin(admin.ModelAdmin):
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

class BulkPaymentAdmin(admin.ModelAdmin):
	list_display = ['adminstring', 'conference', 'user', 'numregs', 'paidat', 'ispaid',]
	list_filter = ['conference', ]

admin.site.register(Conference, ConferenceAdmin)
admin.site.register(RegistrationClass, RegistrationClassAdmin)
admin.site.register(RegistrationDay, RegistrationDayAdmin)
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
admin.site.register(ConferenceFeedbackAnswer, ConferenceFeedbackAnswerAdmin)
admin.site.register(PrepaidBatch, PrepaidBatchAdmin)
admin.site.register(PrepaidVoucher, PrepaidVoucherAdmin)
admin.site.register(BulkPayment, BulkPaymentAdmin)
