from django.contrib import admin
from postgresqleu.newsevents.models import News, Event

admin.site.register(Event)
admin.site.register(News)
