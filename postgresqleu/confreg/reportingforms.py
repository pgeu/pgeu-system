from django import forms
from django.http import Http404

from .models import Conference
from .reporting import reporttypes

from postgresqleu.util.forms import GroupedModelMultipleChoiceField

_trendlines = (
    ('', 'None'),
    ('linear', 'Linear'),
    ('exponential', 'Exponential'),
    ('polynomial', 'Polynomial'),
)


class TimeReportForm(forms.Form):
    reporttype = forms.ChoiceField(required=True, choices=enumerate([r[0] for r in reporttypes], 1), label="Report type")
    conferences = GroupedModelMultipleChoiceField('series', required=True, queryset=Conference.objects.all().order_by('-startdate'))
    trendline = forms.ChoiceField(required=False, choices=_trendlines)

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(TimeReportForm, self).__init__(*args, **kwargs)

        if not self.user.is_superuser:
            self.fields['conferences'].queryset = Conference.objects.filter(series__administrators=self.user)


class QueuePartitionForm(forms.Form):
    report = forms.CharField(required=True, widget=forms.HiddenInput())
    partitions = forms.IntegerField(required=True, label="Number of partitions")

    def build_query(self, conference):
        if conference.queuepartitioning == 1:
            partitionfield = 'lastname'
        elif conference.queuepartitioning == 2:
            partitionfield = 'firstname'
        else:
            raise Http404("Queue partitioning not enabled for this conference")

        return """WITH t AS (
 SELECT
  CASE WHEN upper(substring({0}, 1, 1)) BETWEEN 'A' AND 'Z' THEN upper(substring({0}, 1, 1)) ELSE NULL END AS letter,
  count(*) AS num
 FROM confreg_conferenceregistration
 WHERE conference_id=%(confid)s AND payconfirmedat IS NOT NULL AND canceledat IS NULL
  GROUP BY 1
), t2 AS (
 SELECT letter,
  num,
  sum(num) OVER (ORDER BY letter) / sum(num) OVER () AS part
FROM t
), g AS (
 SELECT gg, gg/(%(partitions)s::double precision) AS ggg from generate_series(1,%(partitions)s) gg(gg)
), t3 as (
 SELECT letter, num, part, (SELECT gg FROM g WHERE ggg >= part ORDER BY ggg LIMIT 1) AS bucket
 FROM t2
)
SELECT
 string_agg(CASE WHEN letter IS NULL THEN 'Other' ELSE letter END, ', ') AS "Letters",
 sum(num) AS "Number in partition"
FROM t3 GROUP BY bucket order by 1
""".format(partitionfield)

    def extra_params(self):
        return {
            'partitions': self.cleaned_data['partitions'],
        }
