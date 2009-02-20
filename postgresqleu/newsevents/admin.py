from django.contrib import admin
from postgresqleu.newsevents.models import *

admin.site.register(Event)
admin.site.register(News)
