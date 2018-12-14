from django import forms

from models import Conference
from reporting import reporttypes

from postgresqleu.util.forms import GroupedModelMultipleChoiceField

_trendlines = (
    ('', 'None'),
    ('linear', 'Linear'),
    ('exponential', 'Exponential'),
    ('polynomial', 'Polynomial'),
)

class TimeReportForm(forms.Form):
    reporttype = forms.ChoiceField(required=True, choices=enumerate([r[0] for r in reporttypes],1), label="Report type")
    conferences = GroupedModelMultipleChoiceField('series', required=True, queryset=Conference.objects.all().order_by('-startdate'))
    trendline = forms.ChoiceField(required=False, choices=_trendlines)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(TimeReportForm, self).__init__(*args, **kwargs)

        if not self.user.is_superuser:
            self.fields['conferences'].queryset = Conference.objects.filter(series__administrators=self.user)

