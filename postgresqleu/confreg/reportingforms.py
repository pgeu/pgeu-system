from django import forms

from models import Conference
from reporting import reporttypes

class TimeReportForm(forms.Form):
	reporttype = forms.ChoiceField(required=True, choices=enumerate([r[0] for r in reporttypes],1))
	conferences = forms.ModelMultipleChoiceField(required=True, queryset=Conference.objects.all())
