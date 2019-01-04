from django.contrib import admin
from django.utils.safestring import mark_safe
from django.urls import reverse

from .models import TrustlyTransaction, TrustlyRawNotification, TrustlyNotification, TrustlyLog


class TrustlyTransactionAdmin(admin.ModelAdmin):
    list_display = ('orderid', 'invoiceid', 'amount', 'createdat', 'pendingat', 'completedat',)


class TrustlyRawNotificationAdmin(admin.ModelAdmin):
    list_display = ('dat', 'confirmed')
    readonly_fields = ('notification_link',)

    def notification_link(self, obj):
        if obj.trustlynotification_set.exists():
            n = obj.trustlynotification_set.all()[0]
            url = reverse('admin:trustlypayment_trustlynotification_change', args=(n.id,))
            return mark_safe('<a href="{0}">{1}</a>'.format(url, n))
    notification_link.short_description = 'Notification'


class TrustlyNotificationAdmin(admin.ModelAdmin):
    list_display = ('receivedat', 'notificationid', 'orderid', 'method', 'amount', 'confirmed')
    readonly_fields = ('rawnotification_link',)
    exclude = ('rawnotification',)

    def rawnotification_link(self, obj):
        url = reverse('admin:trustlypayment_trustlyrawnotification_change', args=(obj.rawnotification.id, ))
        return mark_safe('<a href="{0}">{1}</a>'.format(url, obj))
    rawnotification_link.short_description = 'Rawnotification'


class TrustlyLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'success', 'sentstr', 'message', )

    def success(self, obj):
        return not obj.error
    success.boolean = True

    def sentstr(self, obj):
        return obj.sent and 'Yes' or 'No'
    sentstr.short_description = 'Log sent'


admin.site.register(TrustlyTransaction, TrustlyTransactionAdmin)
admin.site.register(TrustlyRawNotification, TrustlyRawNotificationAdmin)
admin.site.register(TrustlyNotification, TrustlyNotificationAdmin)
admin.site.register(TrustlyLog, TrustlyLogAdmin)
