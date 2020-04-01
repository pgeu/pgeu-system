from django.contrib import admin
from django.forms import ValidationError, ModelForm

from .models import Vote, Election, Candidate


class VoteAdminForm(ModelForm):
    class Meta:
        model = Vote
        exclude = []

    def clean(self):
        raise ValidationError("You really shouldn't edit votes! If you *really* need to fix something broken, do it in the db")


class VoteAdmin(admin.ModelAdmin):
    list_display = ('election', 'voter', 'candidate', 'score')
    autocomplete_fields = ('voter', )
    ordering = ['election', ]
    form = VoteAdminForm


class ElectionAdmin(admin.ModelAdmin):
    list_display = ['name', 'startdate', 'enddate', ]
    ordering = ['-startdate', ]


class CandidateAdmin(admin.ModelAdmin):
    list_display = ['name', 'election', ]
    list_filter = ['election', ]
    ordering = ['name', ]


admin.site.register(Election, ElectionAdmin)
admin.site.register(Candidate, CandidateAdmin)
admin.site.register(Vote, VoteAdmin)
