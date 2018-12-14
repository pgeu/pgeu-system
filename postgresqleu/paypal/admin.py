from django.contrib import admin
from models import SourceAccount, TransactionInfo, ErrorLog

class TransactionInfoAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'sourceaccount', 'sender', 'amount', 'fee', 'transtext', 'matched', )
    list_filter = ('sourceaccount', 'matched', )
    ordering = ('-timestamp', )
    search_fields = ('paypaltransid', 'sender', 'sendername', 'transtext',)

class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'sent', 'message', )
    list_filter = ('sent', )
    ordering = ('-timestamp', )

admin.site.register(SourceAccount)
admin.site.register(TransactionInfo, TransactionInfoAdmin)
admin.site.register(ErrorLog, ErrorLogAdmin)
