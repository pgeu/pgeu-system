from django import forms

from models import Conference

class TimeReportForm(forms.Form):
	reporttype = forms.ChoiceField(required=True, choices=(
		(1, 'Confirmed registrations'),
		(2, 'Submissions'),
		(3, 'Registration types'),
	))
	conferences = forms.ModelMultipleChoiceField(required=True, queryset=Conference.objects.all())
