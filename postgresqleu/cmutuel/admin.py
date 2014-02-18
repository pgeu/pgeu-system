from django.contrib import admin

from models import CMutuelTransaction

class CMutuelTransactionAdmin(admin.ModelAdmin):
	list_display = ('opdate', 'amount', 'description', 'balance', 'sent', )

admin.site.register(CMutuelTransaction, CMutuelTransactionAdmin)
