import csv
from collections import OrderedDict

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Conference, ConferenceRegistration, DiversitySurveyAnswer
from .util import get_authenticated_conference, render_conference_response


_AGGREGATE_FIELDS = (
    'age_range', 'gender_identity', 'ethnicity', 'career_level',
    'years_in_tech', 'education_level', 'company_size',
    'first_time_attendee', 'how_heard',
)

# Characters that spreadsheets interpret as formula triggers in CSV cells.
_CSV_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def _csv_safe(value):
    s = '' if value is None else str(value)
    if s and s[0] in _CSV_FORMULA_PREFIXES:
        s = "'" + s
    return s


class DiversitySurveyForm(forms.ModelForm):
    class Meta:
        model = DiversitySurveyAnswer
        fields = [
            'age_range', 'gender_identity', 'ethnicity', 'career_level',
            'years_in_tech', 'education_level', 'company_size',
            'first_time_attendee', 'how_heard', 'accessibility_needs',
        ]
        widgets = {
            'accessibility_needs': forms.Textarea(attrs={'rows': 3, 'cols': 60}),
        }


def _set_response(registration, value):
    # Use .update() so ConferenceRegistration.lastmodified does NOT change.
    # If it did, the lastmodified timestamp would leak the response time and
    # could be correlated with DiversitySurveyAnswer rows, breaking anonymity.
    ConferenceRegistration.objects.filter(pk=registration.pk).update(diversity_survey_response=value)


@login_required
@transaction.atomic
def diversity_survey(request, confname):
    conference = get_object_or_404(Conference, urlname=confname)
    if not conference.diversity_survey_enabled:
        raise Http404
    try:
        registration = ConferenceRegistration.objects.get(
            conference=conference, attendee=request.user, canceledat__isnull=True)
    except ConferenceRegistration.DoesNotExist:
        messages.error(request, "You must be registered for this conference to take the survey.")
        return redirect('/events/{}/'.format(confname))

    if registration.diversity_survey_response is True:
        return render_conference_response(request, conference, 'reg', 'confreg/diversity_survey.html', {
            'form': None, 'already_submitted': True, 'declined': False,
        })

    if request.method == 'POST':
        if 'skip' in request.POST:
            _set_response(registration, False)
            messages.info(request, "You can take the diversity survey later from your registration dashboard.")
            return redirect('../')
        form = DiversitySurveyForm(request.POST)
        if form.is_valid():
            answer = form.save(commit=False)
            answer.conference = conference
            answer.save()
            _set_response(registration, True)
            messages.success(request, "Thank you for completing the diversity survey!")
            return redirect('../')
    else:
        form = DiversitySurveyForm()

    return render_conference_response(request, conference, 'reg', 'confreg/diversity_survey.html', {
        'form': form,
        'already_submitted': False,
        'declined': registration.diversity_survey_response is False,
    })


def _build_survey_aggregate(conference):
    answers = DiversitySurveyAnswer.objects.filter(conference=conference)
    regs = ConferenceRegistration.objects.filter(conference=conference)
    submitted = answers.count()
    declined = regs.filter(diversity_survey_response=False).count()

    def pct(n):
        return round(n * 100.0 / submitted, 1) if submitted else 0.0

    sections = []
    for field_name in _AGGREGATE_FIELDS:
        field = DiversitySurveyAnswer._meta.get_field(field_name)
        labels = OrderedDict(field.choices)
        counts = dict(answers.values_list(field_name).annotate(n=Count('id')))
        rows = [(label, counts.get(value, 0), pct(counts.get(value, 0)))
                for value, label in labels.items()]
        sections.append({'label': field.verbose_name, 'rows': rows})

    accessibility_notes = list(answers.exclude(accessibility_needs='').values_list('accessibility_needs', flat=True))
    return submitted, declined, sections, accessibility_notes


def diversity_survey_report(request, urlname):
    conference = get_authenticated_conference(request, urlname)
    submitted, declined, sections, accessibility_notes = _build_survey_aggregate(conference)

    if request.GET.get('format') == 'csv':
        resp = HttpResponse(content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = 'attachment; filename="diversity_survey_{}.csv"'.format(conference.urlname)
        w = csv.writer(resp, delimiter=';', quoting=csv.QUOTE_ALL)
        w.writerow([_csv_safe(v) for v in ['Diversity survey report', conference.conferencename]])
        w.writerow([_csv_safe(v) for v in ['Submitted', submitted]])
        w.writerow([_csv_safe(v) for v in ['Declined', declined]])
        for section in sections:
            w.writerow([])
            w.writerow([_csv_safe(v) for v in [section['label'], 'Count', 'Percent']])
            for label, count, percent in section['rows']:
                w.writerow([_csv_safe(label), _csv_safe(count), _csv_safe('{}%'.format(percent))])
        if accessibility_notes:
            w.writerow([])
            w.writerow([_csv_safe('Accessibility accommodations used')])
            for note in accessibility_notes:
                w.writerow([_csv_safe(note)])
        return resp

    return render(request, 'confreg/admin_diversity_report.html', {
        'conference': conference,
        'helplink': 'reports#diversity',
        'submitted_count': submitted,
        'declined_count': declined,
        'sections': sections,
        'accessibility_notes': accessibility_notes,
    })
