from django.contrib import admin
from django import forms
from django.http import HttpResponseRedirect
from django.forms import ValidationError
from django.forms.utils import ErrorList
from django.db.models.fields.files import ImageFieldFile
from django.db.models import Count
from django.core import urlresolvers
from django.utils.safestring import mark_safe
from django.contrib.postgres.forms.ranges import RangeWidget

from models import Conference, ConferenceRegistration, RegistrationType, Speaker
from models import ConferenceSession, Track, Room, ConferenceSessionScheduleSlot
from models import RegistrationClass, RegistrationDay, AttendeeMail
from models import ShirtSize, ConferenceAdditionalOption
from models import ConferenceFeedbackQuestion, Speaker_Photo
from models import PrepaidVoucher, PrepaidBatch, BulkPayment, DiscountCode
from models import PendingAdditionalOrder
from models import VolunteerSlot

from selectable.forms.widgets import AutoCompleteSelectWidget, AutoCompleteSelectMultipleWidget
from postgresqleu.accountinfo.lookups import UserLookup
from postgresqleu.confreg.lookups import RegistrationLookup
from postgresqleu.util.admin import SelectableWidgetAdminFormMixin
from postgresqleu.util.forms import ConcurrentProtectedModelForm

from util import notify_reg_confirmed

from postgresqleu.confreg.dbimage import InlinePhotoWidget
from postgresqleu.accounting.models import Object
from postgresqleu.confsponsor.models import Sponsor

from datetime import datetime
import urllib

#
# List filters
#
class TrackListFilter(admin.SimpleListFilter):
	title = 'Track'
	parameter_name = 'track'
	def lookups(self, request, model_admin):
		cid = request.GET.get('conference__id__exact', -1)
		if cid >= 0:
			return ((t.id, t.trackname) for t in Track.objects.filter(conference__id=cid))

	def queryset(self, request, queryset):
		if self.value():
			return queryset.filter(track_id=self.value())

class RegtypeListFilter(admin.SimpleListFilter):
	title = 'Registration type'
	parameter_name = 'regtype'
	def lookups(self, request, model_admin):
		cid = request.GET.get('conference__id__exact', -1)
		if cid >= 0:
			return ((r.id, r.regtype) for r in RegistrationType.objects.filter(conference__id=cid))

	def queryset(self, request, queryset):
		if self.value():
			return queryset.filter(regtype_id=self.value())

class AdditionalOptionListFilter(admin.SimpleListFilter):
	title = 'Additional option'
	parameter_name = 'addoption'
	def lookups(self, request, model_admin):
		cid = request.GET.get('conference__id__exact', -1)
		if cid >= 0:
			return ((ao.id, ao.name) for ao in ConferenceAdditionalOption.objects.filter(conference__id=cid))

	def queryset(self, request, queryset):
		if self.value():
			return queryset.filter(additionaloptions__id=self.value())

#
# General admin classes
#
class ConferenceAdminForm(SelectableWidgetAdminFormMixin, ConcurrentProtectedModelForm):
	class Meta:
		model = Conference
		exclude = []
		widgets = {
			'administrators': AutoCompleteSelectMultipleWidget(lookup_class=UserLookup),
			'testers': AutoCompleteSelectMultipleWidget(lookup_class=UserLookup),
			'talkvoters': AutoCompleteSelectMultipleWidget(lookup_class=UserLookup),
			'staff': AutoCompleteSelectMultipleWidget(lookup_class=UserLookup),
			'volunteers': AutoCompleteSelectMultipleWidget(lookup_class=RegistrationLookup)
		}
	accounting_object = forms.ChoiceField(choices=[], required=False)

	def __init__(self, *args, **kwargs):
		super(ConferenceAdminForm, self).__init__(*args, **kwargs)
		self.fields['volunteers'].widget.widget.update_query_parameters({'conference': self.instance.id})
		self.fields['accounting_object'].choices = [('', '----'),] + [(o.name, o.name) for o in Object.objects.filter(active=True)]

	def clean(self):
		data = super(ConferenceAdminForm, self).clean()

		if data['jinjadir']:
			for f in ('basetemplate', 'templatemodule', 'templateoverridedir', 'templatemediabase', 'badgemodule'):
				if data[f]:
					raise ValidationError('Cannot use {0} together with jinjadir'.format(f))

		return data

class ConferenceAdmin(admin.ModelAdmin):
	form = ConferenceAdminForm
	list_display = ('conferencename', 'active', 'callforpapersopen', 'callforsponsorsopen', 'feedbackopen', 'startdate', 'enddate')
	ordering = ('-startdate', )

class ConferenceRegistrationForm(SelectableWidgetAdminFormMixin, ConcurrentProtectedModelForm):
	class Meta:
		model = ConferenceRegistration
		exclude = []
		widgets = {
			'attendee': AutoCompleteSelectWidget(lookup_class=UserLookup),
		}

	def __init__(self, *args, **kwargs):
		super(ConferenceRegistrationForm, self).__init__(*args, **kwargs)
		if 'instance' in kwargs:
			self.fields['additionaloptions'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.instance.conference)
			self.fields['regtype'].queryset = RegistrationType.objects.filter(conference=self.instance.conference)
			self.fields['payconfirmedat'].help_text = self.fields['payconfirmedby'].help_text = "Don't edit this field here - instead, go back to the list of registrations and chose to approve from there!"


class ConferenceRegistrationAdmin(admin.ModelAdmin):
	form = ConferenceRegistrationForm
	list_display = ['email', 'conference', 'firstname', 'lastname', 'created_short', 'short_regtype', 'payconfirmedat_short', 'has_invoice']
	list_filter = ['conference', RegtypeListFilter, AdditionalOptionListFilter, ]
	search_fields = ['email', 'firstname', 'lastname', ]
	ordering = ['-payconfirmedat', '-created', 'lastname', 'firstname', ]
	actions= ['approve_conferenceregistration', 'email_recipients']
	filter_horizontal = ('additionaloptions',)
	exclude = ('invoice','bulkpayment',)
	readonly_fields = ('invoice_link','bulkpayment_link', 'lastmodified', )

	def get_queryset(self, request):
		qs = super(ConferenceRegistrationAdmin, self).get_queryset(request)

		if request.user.is_superuser:
			return qs
		else:
			return qs.filter(conference__administrators=request.user)

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
		# We loop over them and update, so we can send notifications.
		# Not as efficient, but there are never that many to approve
		# anyway...
		num = 0
		for reg in queryset.filter(payconfirmedat__isnull=True):
			reg.payconfirmedat = datetime.today()
			reg.payconfirmedby = request.user.username
			reg.save()
			notify_reg_confirmed(reg)
			num += 1
		self.message_user(request, '%s registration(s) marked as confirmed.' % num)
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

class ConferenceSessionForm(ConcurrentProtectedModelForm):
	class Meta:
		model = ConferenceSession
		exclude = []

	def __init__(self, *args, **kwargs):
		super(ConferenceSessionForm, self).__init__(*args, **kwargs)
		if 'instance' in kwargs and self.instance.conference_id:
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
	list_filter = ['conference', TrackListFilter, 'status', ]
	search_fields = ['title', ]
	filter_horizontal = ('speaker',)
	actions= ['email_recipients', ]

	def get_queryset(self, request):
		qs = super(ConferenceSessionAdmin, self).get_queryset(request)
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

class RegistrationTypeAdminForm(ConcurrentProtectedModelForm):
	class Meta:
		model = RegistrationType
		exclude = []

	def __init__(self, *args, **kwargs):
		super(RegistrationTypeAdminForm, self).__init__(*args, **kwargs)
		try:
			self.fields['regclass'].queryset = RegistrationClass.objects.filter(conference=self.instance.conference)
			self.fields['days'].queryset = RegistrationDay.objects.filter(conference=self.instance.conference)
			self.fields['requires_option'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.instance.conference)
			if self.instance.conference.invoice_autocancel_hours:
				self.fields['invoice_autocancel_hours'].help_text = "Automatically cancel invoices after this many hours. Conference settings currently override this to minimum value {0}.".format(self.instance.conference.invoice_autocancel_hours)
		except Conference.DoesNotExist:
			# If we don't have a conference yet, we can just ignore the fact
			# that we couldn't list it.
			pass

class RegistrationTypeAdmin(admin.ModelAdmin):
	list_display = ['conference', 'regtype', 'cost', 'sortkey', 'active', 'activeuntil', ]
	list_filter = ['conference',]
	ordering = ['conference','regtype']
	filter_horizontal = ('requires_option',)
	form = RegistrationTypeAdminForm

class ShirtsizeAdmin(admin.ModelAdmin):
	list_display = ['shirtsize', 'sortkey', ]

class ConferenceAdditionalOptionAdminForm(ConcurrentProtectedModelForm):
	class Meta:
		model = ConferenceAdditionalOption
		exclude = []

	def __init__(self, *args, **kwargs):
		super(ConferenceAdditionalOptionAdminForm, self).__init__(*args, **kwargs)
		try:
			self.fields['requires_regtype'].queryset = RegistrationType.objects.filter(conference=self.instance.conference)
			self.fields['mutually_exclusive'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.instance.conference)
		except Conference.DoesNotExist:
			# If we don't have a conference yet, we can just ignore the fact
			# that we couldn't list it.
			pass

class ConferenceAdditionalOptionAdmin(admin.ModelAdmin):
	list_display = ['conference', 'name', 'maxcount', 'cost', 'used_count', 'confirmed_count', 'unconfirmed_count']
	list_filter = ['conference', ]
	ordering = ['conference', 'name', ]
	filter_horizontal = ('requires_regtype', 'mutually_exclusive', )
	form = ConferenceAdditionalOptionAdminForm

	def get_queryset(self, request):
		return ConferenceAdditionalOption.objects.extra(select={
			'confirmed_count': 'SELECT count(*) FROM confreg_conferenceregistration r INNER JOIN confreg_conferenceregistration_additionaloptions cao ON cao.conferenceregistration_id=r.id WHERE cao.conferenceadditionaloption_id=confreg_conferenceadditionaloption.id AND r.payconfirmedat IS NOT NULL',
			'unconfirmed_count': 'SELECT count(*) FROM confreg_conferenceregistration r INNER JOIN confreg_conferenceregistration_additionaloptions cao ON cao.conferenceregistration_id=r.id WHERE cao.conferenceadditionaloption_id=confreg_conferenceadditionaloption.id AND r.payconfirmedat IS NULL',
			})
		return ConferenceAdditionalOption.objects.annotate(reg_count=Count('conferenceregistration'))

	def confirmed_count(self, inst):
		return inst.confirmed_count
	confirmed_count.short_description = 'Confirmed'

	def unconfirmed_count(self, inst):
		return inst.unconfirmed_count
	unconfirmed_count.short_description = 'Unconfirmed'

	def used_count(self, inst):
		return inst.confirmed_count + inst.unconfirmed_count
	used_count.short_description = 'Total used'

class SpeakerAdminForm(ConcurrentProtectedModelForm):
	class Meta:
		model = Speaker
		exclude = []

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
	search_fields = ['fullname', 'user__email']
	ordering = ['fullname']
	form = SpeakerAdminForm

class SpeakerPhotoAdmin(admin.ModelAdmin):
	def formfield_for_dbfield(self, db_field, **kwargs):
		if db_field.name == 'photo':
			kwargs['widget'] = InlinePhotoWidget
		return super(SpeakerPhotoAdmin,self).formfield_for_dbfield(db_field,**kwargs)

class TrackAdmin(admin.ModelAdmin):
	list_filter = ['conference', ]
	list_display = ['conference', 'trackname', 'sortkey', 'color', 'incfp', ]

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

class PrepaidBatchAdminForm(SelectableWidgetAdminFormMixin, ConcurrentProtectedModelForm):
	class Meta:
		model = PrepaidBatch
		exclude = []
		widgets = {
			'buyer': AutoCompleteSelectWidget(lookup_class=UserLookup),
		}

	def __init__(self, *args, **kwargs):
		super(PrepaidBatchAdminForm, self).__init__(*args, **kwargs)
		try:
			self.fields['sponsor'].queryset = Sponsor.objects.filter(conference=self.instance.conference)
		except Conference.DoesNotExist:
			pass


class PrepaidBatchAdmin(admin.ModelAdmin):
	list_display = ['id', 'conference', 'buyer', 'buyername', 'total_num', 'used_num' ]
	list_filter = ['conference', ]
	inlines = [PrepaidVoucherInline, ]
	form = PrepaidBatchAdminForm

	def get_queryset(self, request):
		return PrepaidBatch.objects.extra(select={
			'num': 'SELECT count(*) FROM confreg_prepaidvoucher WHERE batch_id=confreg_prepaidbatch.id',
			'used': 'SELECT count(*) FROM confreg_prepaidvoucher WHERE batch_id=confreg_prepaidbatch.id AND usedate IS NOT NULL',
			})

	def total_num(self, inst):
		return inst.num
	total_num.short_description = 'Total vouchers'

	def used_num(self, inst):
		return inst.used
	used_num.short_description = 'Used vouchers'

class PrepaidVoucherAdminForm(SelectableWidgetAdminFormMixin, ConcurrentProtectedModelForm):
	class Meta:
		model = PrepaidVoucher
		exclude = []
		widgets = {
			'user': AutoCompleteSelectWidget(lookup_class=RegistrationLookup),
		}

	def __init__(self, *args, **kwargs):
		super(PrepaidVoucherAdminForm, self).__init__(*args, **kwargs)
		try:
			self.fields['batch'].queryset = PrepaidBatch.objects.filter(conference=self.instance.conference)
			self.fields['user'].widget.widget.update_query_parameters({'conference': self.instance.conference.id})
			self.fields['user'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
		except Conference.DoesNotExist:
			pass

class PrepaidVoucherAdmin(admin.ModelAdmin):
	list_display = ['vouchervalue', 'conference', 'buyername', 'usedby', 'usedate', ]
	list_filter = ['conference', ]
	form = PrepaidVoucherAdminForm

	def buyername(self, obj):
		url = urlresolvers.reverse('admin:confreg_prepaidbatch_change', args=(obj.batch.pk,))
		return mark_safe('<a href="%s">%s</a>' % (url, obj.batch.buyername))
	buyername.allow_tags = True

	def usedby(self, obj):
		if obj.user:
			return "%s %s" % (obj.user.firstname, obj.user.lastname)
		return None

class DiscountCodeAdminForm(SelectableWidgetAdminFormMixin, ConcurrentProtectedModelForm):
	class Meta:
		model = DiscountCode
		exclude = []
		widgets = {
			'sponsor_rep': AutoCompleteSelectWidget(lookup_class=UserLookup),
			'registrations': AutoCompleteSelectMultipleWidget(lookup_class=RegistrationLookup),
		}

	def __init__(self, *args, **kwargs):
		super(DiscountCodeAdminForm, self).__init__(*args, **kwargs)
		try:
			self.fields['registrations'].widget.widget.update_query_parameters({'conference': self.instance.conference.id})
			self.fields['registrations'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.conference)
			self.fields['requiresoption'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.instance.conference)
			self.fields['requiresregtype'].queryset = RegistrationType.objects.filter(conference=self.instance.conference)
			self.fields['sponsor'].queryset = Sponsor.objects.filter(conference=self.instance.conference)
		except Conference.DoesNotExist:
			pass

	def clean_discountpercentage(self):
		if int(self.cleaned_data['discountpercentage']) < 0:
			raise ValidationError('Discount percentage must be a positive number or zero!')
		if int(self.cleaned_data['discountpercentage']) > 100:
			raise ValidationError('Discount percentage cannot be higher than 100!')
		return self.cleaned_data['discountpercentage']

	def clean_maxuses(self):
		if int(self.cleaned_data['maxuses']) < 0:
			raise ValidationError('Max uses must be a positive number or zero!')
		return self.cleaned_data['maxuses']

	def clean(self):
		cleaned_data = super(DiscountCodeAdminForm, self).clean()

		if cleaned_data.has_key('discountamount') and cleaned_data.has_key('discountpercentage'):
			if cleaned_data['discountamount'] > 0 and cleaned_data['discountpercentage'] > 0:
				raise ValidationError('Cannot specify both discount amount and discount percentage at the same time!')

		if cleaned_data.has_key('discountamount') and cleaned_data.has_key('regonly'):
			if cleaned_data['discountamount'] > 0 and cleaned_data['regonly']:
				raise ValidationError('Regonly field can only be set for percentage discounts!')

		if cleaned_data.get('sponsor', None) and not cleaned_data.get('sponsor_rep', None):
			self._errors['sponsor_rep'] = ErrorList(["Sponsor rep must be given if sponsor is given!"])
		if cleaned_data.get('sponsor_rep', None) and not cleaned_data.get('sponsor', None):
			self._errors['sponsor'] = ErrorList(["Sponsor must be given if sponsor rep is given!"])

		return cleaned_data

class DiscountCodeAdmin(admin.ModelAdmin):
	list_display = ['code', 'conference', 'maxuses', 'count', ]
	list_filter = ['conference', ]
	form = DiscountCodeAdminForm

class BulkPaymentAdminForm(SelectableWidgetAdminFormMixin, ConcurrentProtectedModelForm):
	class Meta:
		model = BulkPayment
		exclude = []
		widgets = {
			'user': AutoCompleteSelectWidget(lookup_class=UserLookup),
		}

class BulkPaymentAdmin(admin.ModelAdmin):
	form = BulkPaymentAdminForm
	list_display = ['adminstring', 'conference', 'user', 'numregs', 'paidat', 'ispaid',]
	list_filter = ['conference', ]

class AttendeeMailAdminForm(ConcurrentProtectedModelForm):
	class Meta:
		model = AttendeeMail
		exclude = []

	def __init__(self, *args, **kwargs):
		super(AttendeeMailAdminForm, self).__init__(*args, **kwargs)
		if 'instance' in kwargs:
			self.fields['regclasses'].queryset = RegistrationClass.objects.filter(conference=self.instance.conference)

class AttendeeMailAdmin(admin.ModelAdmin):
	form = AttendeeMailAdminForm
	filter_horizontal = ('regclasses', )

class PendingAdditionalOrderAdminForm(ConcurrentProtectedModelForm):
	class Meta:
		model = PendingAdditionalOrder
		exclude = []

	def __init__(self, *args, **kwargs):
		super(PendingAdditionalOrderAdminForm, self).__init__(*args, **kwargs)
		if 'instance' in kwargs:
			self.fields['reg'].queryset = ConferenceRegistration.objects.filter(conference=self.instance.reg.conference)
			self.fields['options'].queryset = ConferenceAdditionalOption.objects.filter(conference=self.instance.reg.conference)
			self.fields['newregtype'].queryset = RegistrationType.objects.filter(conference=self.instance.reg.conference)

class PendingAdditionalOrderAdmin(admin.ModelAdmin):
	form = PendingAdditionalOrderAdminForm
	list_display = ('reg', 'createtime', 'payconfirmedat')

class VolunteerSlotAdminForm(ConcurrentProtectedModelForm):
	class Meta:
		model = VolunteerSlot
		exclude = []
		widgets = {
			'timerange': RangeWidget(admin.widgets.AdminSplitDateTime()),
		}

	def clean(self):
		data = super(VolunteerSlotAdminForm, self).clean()

		if data['max_staff'] < data['min_staff']:
			raise ValidationError("Max staff can't be less than min staff!")
		return data

class VolunteerSlotAdmin(admin.ModelAdmin):
	form = VolunteerSlotAdminForm
	list_filter = ['conference', ]
	list_display = ('__unicode__', 'title')


admin.site.register(Conference, ConferenceAdmin)
admin.site.register(RegistrationClass, RegistrationClassAdmin)
admin.site.register(RegistrationDay, RegistrationDayAdmin)
admin.site.register(RegistrationType, RegistrationTypeAdmin)
admin.site.register(ShirtSize, ShirtsizeAdmin)
admin.site.register(ConferenceRegistration, ConferenceRegistrationAdmin)
admin.site.register(ConferenceSession, ConferenceSessionAdmin)
admin.site.register(ConferenceSessionScheduleSlot, ConferenceSessionScheduleSlotAdmin)
admin.site.register(Track, TrackAdmin)
admin.site.register(Room, RoomAdmin)
admin.site.register(Speaker, SpeakerAdmin)
admin.site.register(Speaker_Photo, SpeakerPhotoAdmin)
admin.site.register(ConferenceAdditionalOption, ConferenceAdditionalOptionAdmin)
admin.site.register(ConferenceFeedbackQuestion, ConferenceFeedbackQuestionAdmin)
admin.site.register(PrepaidBatch, PrepaidBatchAdmin)
admin.site.register(PrepaidVoucher, PrepaidVoucherAdmin)
admin.site.register(DiscountCode, DiscountCodeAdmin)
admin.site.register(BulkPayment, BulkPaymentAdmin)
admin.site.register(AttendeeMail, AttendeeMailAdmin)
admin.site.register(PendingAdditionalOrder, PendingAdditionalOrderAdmin)
admin.site.register(VolunteerSlot, VolunteerSlotAdmin)
