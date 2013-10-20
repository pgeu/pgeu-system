from django.contrib import admin
from django.utils.safestring import mark_safe
from django.core import urlresolvers

from models import RawNotification, Notification
from models import Report, TransactionStatus, AdyenLog

class RawNotificationAdmin(admin.ModelAdmin):
	list_display = ('dat', 'confirmed',)

class NotificationAdmin(admin.ModelAdmin):
	list_display = ('receivedat', 'eventDate', 'merchantAccountCode', 'eventCode', 'live', 'success', 'confirmed', 'pspReference', )
	readonly_fields = ('rawnotification_link',)
	exclude = ('rawnotification', )

	def rawnotification_link(self, obj):
		url = urlresolvers.reverse('admin:adyen_rawnotification_change', args=(obj.rawnotification.id,))
		return mark_safe('<a href="%s">%s</a>' % (url, obj))
	rawnotification_link.short_description = 'Rawnotification'

class ReportAdmin(admin.ModelAdmin):
	list_display = ('receivedat', 'downloadedat', 'processedat', 'url',)

class TransactionStatusAdmin(admin.ModelAdmin):
	list_display = ('pspReference', 'amount', 'settledamount', 'authorizedat', 'capturedat', 'settledat', 'method' )

class AdyenLogAdmin(admin.ModelAdmin):
	list_display = ('timestamp', 'success', 'sentstr', 'pspReference', 'message', )

	def success(self, obj):
		return not obj.error
	success.boolean=True

	def sentstr(self, obj):
		return obj.sent and 'Yes' or 'No'
	sentstr.short_description='Log sent'

admin.site.register(RawNotification, RawNotificationAdmin)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(Report, ReportAdmin)
admin.site.register(TransactionStatus, TransactionStatusAdmin)
admin.site.register(AdyenLog, AdyenLogAdmin)
