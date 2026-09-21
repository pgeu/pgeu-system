from django.contrib import admin

from .models import QontoTransaction


class QontoTransactionAdmin(admin.ModelAdmin):
    list_display = ('qontoid', 'datetime', 'amount', 'paymentref')


admin.site.register(QontoTransaction, QontoTransactionAdmin)
