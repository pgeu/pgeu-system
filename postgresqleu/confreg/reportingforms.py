from django import forms

from models import Conference
from reporting import reporttypes

_trendlines = (
	('', 'None'),
	('linear', 'Linear'),
	('exponential', 'Exponential'),
	('polynomial', 'Polynomial'),
)
class TimeReportForm(forms.Form):
	reporttype = forms.ChoiceField(required=True, choices=enumerate([r[0] for r in reporttypes],1))
	conferences = forms.ModelMultipleChoiceField(required=True, queryset=Conference.objects.all())
	trendline = forms.ChoiceField(required=False, choices=_trendlines)
