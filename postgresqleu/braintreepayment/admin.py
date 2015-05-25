from django.contrib import admin

from models import BraintreeTransaction, BraintreeLog

class BraintreeTransactionAdmin(admin.ModelAdmin):
	list_display = ('transid', 'amount', 'disbursedamount', 'authorizedat', 'settledat', 'disbursedat', 'method')
	search_fields = ('transid',)

class BraintreeLogAdmin(admin.ModelAdmin):
	list_display = ('timestamp', 'success', 'sentstr', 'transid', 'message', )

	def success(self, obj):
		return not obj.error
	success.boolean=True

	def sentstr(self, obj):
		return obj.sent and 'Yes' or 'No'
	sentstr.short_description='Log sent'

admin.site.register(BraintreeTransaction, BraintreeTransactionAdmin)
admin.site.register(BraintreeLog, BraintreeLogAdmin)
