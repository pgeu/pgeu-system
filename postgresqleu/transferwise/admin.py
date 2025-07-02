from django.contrib import admin

from .models import TransferwiseTransaction, TransferwiseRefund, TransferwisePayout


class TransferwiseTransactionAdmin(admin.ModelAdmin):
    list_display = ('twreference', 'datetime', 'amount', 'feeamount', 'paymentref')


class TransferwiseRefundAdmin(admin.ModelAdmin):
    list_display = ('refundid', 'origtransaction', 'transferid', )


class TransferwisePayoutAdmin(admin.ModelAdmin):
    list_display = ('reference', 'amount', 'createdat', 'sentat', 'completedat')


admin.site.register(TransferwiseTransaction, TransferwiseTransactionAdmin)
admin.site.register(TransferwiseRefund, TransferwiseRefundAdmin)
admin.site.register(TransferwisePayout, TransferwisePayoutAdmin)
