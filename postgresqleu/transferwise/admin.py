from django.contrib import admin

from .models import TransferwiseTransaction, TransferwiseRefund


class TransferwiseTransactionAdmin(admin.ModelAdmin):
    list_display = ('twreference', 'datetime', 'amount', 'feeamount', 'paymentref')


class TransferwiseRefundAdmin(admin.ModelAdmin):
    list_display = ('refundid', 'origtransaction', 'transferid', )


admin.site.register(TransferwiseTransaction, TransferwiseTransactionAdmin)
admin.site.register(TransferwiseRefund, TransferwiseRefundAdmin)
