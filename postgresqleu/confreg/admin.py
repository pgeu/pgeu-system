from django.contrib import admin
from postgresqleu.confreg.models import *

class ConferenceRegistrationAdmin(admin.ModelAdmin):
	list_display = ['email', 'conference', 'firstname', 'lastname', 'payconfirmedat', ]
	ordering = ['-payconfirmedat', 'lastname', 'firstname', ]

admin.site.register(Conference)
admin.site.register(RegistrationType)
admin.site.register(ShirtSize)
admin.site.register(ConferenceRegistration, ConferenceRegistrationAdmin)
admin.site.register(PaymentOption)
admin.site.register(ConferenceSession)
admin.site.register(ConferenceSessionFeedback)
