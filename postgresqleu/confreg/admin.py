from django.contrib import admin
from postgresqleu.confreg.models import *

admin.site.register(Conference)
admin.site.register(RegistrationType)
admin.site.register(ShirtSize)
admin.site.register(ConferenceRegistration)
admin.site.register(PaymentOption)
