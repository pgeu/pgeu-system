from django.contrib import admin
from django.forms import ValidationError, ModelForm

from .models import Vote, Election, Candidate


class ElectionAdmin(admin.ModelAdmin):
    list_display = ['name', 'startdate', 'enddate', ]
    ordering = ['-startdate', ]


class CandidateAdmin(admin.ModelAdmin):
    list_display = ['name', 'election', ]
    list_filter = ['election', ]
    ordering = ['name', ]


admin.site.register(Election, ElectionAdmin)
admin.site.register(Candidate, CandidateAdmin)
