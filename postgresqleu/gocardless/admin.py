from django.contrib import admin

from .models import GocardlessTransaction


class GocardlessTransactionAdmin(admin.ModelAdmin):
    list_display = ('transactionid', 'date', 'amount', 'paymentref')


admin.site.register(GocardlessTransaction, GocardlessTransactionAdmin)
