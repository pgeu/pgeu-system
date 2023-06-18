from django.contrib import admin

from .models import PlaidTransaction


class PlaidTransactionAdmin(admin.ModelAdmin):
    list_display = ('transactionid', 'datetime', 'amount', 'paymentref')


admin.site.register(PlaidTransaction, PlaidTransactionAdmin)
