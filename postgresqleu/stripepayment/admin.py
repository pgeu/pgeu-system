from django.contrib import admin

from .models import StripeCheckout, StripeLog


class StripeCheckoutAdmin(admin.ModelAdmin):
    list_display = ('id', 'invoiceid', 'amount', 'fee', 'createdat', 'completedat', )


class StripeLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'success', 'sentstr', 'message', )

    def success(self, obj):
        return not obj.error
    success.boolean = True

    def sentstr(self, obj):
        return obj.sent and 'Yes' or 'No'
    sentstr.short_description = 'Log sent'


admin.site.register(StripeCheckout, StripeCheckoutAdmin)
admin.site.register(StripeLog, StripeLogAdmin)
