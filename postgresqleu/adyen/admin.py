from django.contrib import admin
from django.utils.safestring import mark_safe
from django.urls import reverse

from .models import RawNotification, Notification
from .models import Report, TransactionStatus, AdyenLog, Refund


class RawNotificationAdmin(admin.ModelAdmin):
    list_display = ('dat', 'confirmed',)
    readonly_fields = ('notification_link', )

    def notification_link(self, obj):
        if obj.notification_set.exists():
            n = obj.notification_set.all()[0]
            url = reverse("admin:adyen_notification_change", args=(n.id,))
            return mark_safe('<a href="%s">%s</a>' % (url, n))
    notification_link.short_description = 'Notification'


class NotificationAdmin(admin.ModelAdmin):
    list_display = ('receivedat', 'eventDate', 'merchantAccountCode', 'eventCode', 'live', 'success', 'confirmed', 'pspReference', )
    readonly_fields = ('rawnotification_link',)
    exclude = ('rawnotification', )
    search_fields = ('pspReference', 'merchantReference', 'reason', )

    def rawnotification_link(self, obj):
        url = reverse('admin:adyen_rawnotification_change', args=(obj.rawnotification.id,))
        return mark_safe('<a href="%s">%s</a>' % (url, obj))
    rawnotification_link.short_description = 'Rawnotification'


class MerchantAccountFilter(admin.SimpleListFilter):
    title = 'Merchant account'
    parameter_name = 'merchantaccount'

    def lookups(self, request, model_admin):
        return (('PostgreSqlEUCOM', 'PostgreSqlEUCOM'), ('PostgreSqlEUPOS', 'PostgreSqlEUPOS'), )

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(url__regex='/download/MerchantAccount/{}/'.format(self.value()))
        return queryset


class ReportTypeFilter(admin.SimpleListFilter):
    title = 'Report type'
    parameter_name = 'reporttype'

    _types = {
        'payments_accounting': ('Payments Accounting', r'/payments_accounting_report_\d+_\d+_\d+\.csv'),
        'received_payments': ('Received payments', r'received_payments_report_\d+_\d+_\d+\.csv'),
        'settlement_detail': ('Settlement detail', r'settlement_detail_report_batch_\d+\.csv'),
    }

    def lookups(self, request, model_admin):
        return ((k, v[0]) for k, v in self._types.items())

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(url__regex=self._types[self.value()][1])
        return queryset


class ReportAdmin(admin.ModelAdmin):
    list_display = ('receivedat', 'downloadedat', 'processedat', 'url',)
    list_filter = [MerchantAccountFilter, ReportTypeFilter, ]
    readonly_fields = ('notification_link', )
    exclude = ('notification', )

    def notification_link(self, obj):
        if obj.notification:
            url = reverse("admin:adyen_notification_change", args=(obj.notification.id,))
            return mark_safe('<a href="%s">%s</a>' % (url, obj.notification))
    notification_link.short_description = 'Notification'


class TransactionStatusAdmin(admin.ModelAdmin):
    list_display = ('pspReference', 'amount', 'settledamount', 'authorizedat', 'capturedat', 'settledat', 'method')
    readonly_fields = ('notification_link', 'refund_link', )
    exclude = ('notification', )
    search_fields = ('pspReference', 'notes', )

    def notification_link(self, obj):
        if obj.notification:
            url = reverse("admin:adyen_notification_change", args=(obj.notification.id,))
            return mark_safe('<a href="%s">%s</a>' % (url, obj.notification))
    notification_link.short_description = 'Notification'

    def refund_link(self, obj):
        refunds = list(obj.refund_set.all())
        if refunds:
            return mark_safe(
                "<br/>".join(
                    '%s at <a href="%s">%s</a>' % (r.refund_amount, reverse("admin:adyen_refund_change", args=(r.id,)), r.receivedat)
                    for r in refunds
                )
            )
        else:
            return "Not refunded"
    refund_link.short_description = 'Refund'


class RefundAdmin(admin.ModelAdmin):
    list_display = ('notification', 'receivedat', 'transaction', 'refund_amount')
    readonly_fields = ('notification_link', 'transaction_link', )
    exclude = ('notification', 'transaction', )

    def notification_link(self, obj):
        if obj.notification:
            url = reverse("admin:adyen_notification_change", args=(obj.notification.id,))
            return mark_safe('<a href="%s">%s</a>' % (url, obj.notification))
    notification_link.short_description = 'Notification'

    def transaction_link(self, obj):
        if obj.transaction:
            url = reverse("admin:adyen_transactionstatus_change", args=(obj.transaction.id,))
            return mark_safe('<a href="%s">%s</a>' % (url, obj.transaction.pspReference))
    transaction_link.short_description = 'Transaction'


class AdyenLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'success', 'sentstr', 'pspReference', 'message', )

    def success(self, obj):
        return not obj.error
    success.boolean = True

    def sentstr(self, obj):
        return obj.sent and 'Yes' or 'No'
    sentstr.short_description = 'Log sent'


admin.site.register(RawNotification, RawNotificationAdmin)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(Report, ReportAdmin)
admin.site.register(TransactionStatus, TransactionStatusAdmin)
admin.site.register(Refund, RefundAdmin)
admin.site.register(AdyenLog, AdyenLogAdmin)
