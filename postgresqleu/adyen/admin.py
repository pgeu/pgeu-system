from django.contrib import admin
from django.utils.safestring import mark_safe
from django.core import urlresolvers

from models import RawNotification, Notification
from models import Report, TransactionStatus, AdyenLog

class RawNotificationAdmin(admin.ModelAdmin):
	list_display = ('dat', 'confirmed',)
	readonly_fields = ('notification_link', )

	def notification_link(self, obj):
		if obj.notification_set.exists():
			n = obj.notification_set.all()[0]
			url = urlresolvers.reverse("admin:adyen_notification_change", args=(n.id,))
			return mark_safe('<a href="%s">%s</a>' % (url, n))
	notification_link.short_description = 'Notification'

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
	readonly_fields = ('notification_link', )
	exclude = ('notification', )

	def notification_link(self, obj):
		if obj.notification:
			url = urlresolvers.reverse("admin:adyen_notification_change", args=(obj.notification.id,))
			return mark_safe('<a href="%s">%s</a>' % (url, obj.notification))
	notification_link.short_description = 'Notification'

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
