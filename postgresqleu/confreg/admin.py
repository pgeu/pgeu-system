from django.contrib import admin
from postgresqleu.confreg.models import *

class ConferenceRegistrationAdmin(admin.ModelAdmin):
	list_display = ['email', 'conference', 'firstname', 'lastname', 'regtype', 'payconfirmedat', ]
	ordering = ['-payconfirmedat', 'lastname', 'firstname', ]

class ConferenceSessionFeedbackAdmin(admin.ModelAdmin):
	ordering = ['session']

class RegistrationTypeAdmin(admin.ModelAdmin):
	list_display = ['conference', 'regtype', 'cost', 'active']
	ordering = ['conference','regtype']

admin.site.register(Conference)
admin.site.register(RegistrationType, RegistrationTypeAdmin)
admin.site.register(ShirtSize)
admin.site.register(ConferenceRegistration, ConferenceRegistrationAdmin)
admin.site.register(PaymentOption)
admin.site.register(ConferenceSession)
admin.site.register(ConferenceSessionFeedback, ConferenceSessionFeedbackAdmin)
