from django import forms
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.utils.dateparse import parse_datetime, parse_duration
from postgresqleu.confreg.jinjafunc import JinjaTemplateValidator, render_sandboxed_template

from postgresqleu.util.widgets import MonospaceTextarea
from postgresqleu.confreg.models import ConferenceSession, ConferenceTweetQueue, Track

import datetime
import random


def _timestamps_for_tweets(conference, starttime, interval, randint, num):
    if isinstance(starttime, datetime.datetime):
        t = starttime
    else:
        t = parse_datetime(starttime)

    if isinstance(interval, datetime.time):
        ival = datetime.timedelta(hours=interval.hour, minutes=interval.minute, seconds=interval.second)
    else:
        ival = parse_duration(interval)

    if isinstance(randint, datetime.time):
        rsec = datetime.timedelta(hours=randint.hour, minutes=randint.minute, seconds=randint.second).total_seconds()
    else:
        rsec = parse_duration(randint).total_seconds()

    for i in range(num):
        yield t
        t += ival
        t += datetime.timedelta(seconds=rsec * random.random())
        if t.time() > conference.twitter_timewindow_end:
            t = datetime.datetime.combine(t.date() + datetime.timedelta(days=1), conference.twitter_timewindow_start)


class BaseCampaignForm(forms.Form):
    starttime = forms.DateTimeField(label="Date and time of first tweet", initial=datetime.datetime.now)
    timebetween = forms.TimeField(label="Time between tweets", initial=datetime.time(1, 0, 0))
    timerandom = forms.TimeField(label="Time randomization", initial=datetime.time(0, 10, 0),
                                 help_text="A random time from zero to this is added after each time interval")
    content_template = forms.CharField(max_length=2000,
                                       widget=MonospaceTextarea,
                                       required=True)
    dynamic_preview_fields = ['content_template', ]

    confirm = forms.BooleanField(help_text="Confirm that you want to generate all the tweets for this campaign at this time", required=False)

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        self.field_order = ['starttime', 'timebetween', 'timerandom', 'content_template'] + self.custom_fields + ['confirm', ]

        super(BaseCampaignForm, self).__init__(*args, *kwargs)

        if not all([self.data.get(f) for f in ['starttime', 'timebetween', 'timerandom', 'content_template'] + self.custom_fields]):
            del self.fields['confirm']
        else:
            num = self.get_queryset().count()
            tsl = list(_timestamps_for_tweets(conference,
                                              self.data.get('starttime'),
                                              self.data.get('timebetween'),
                                              self.data.get('timerandom'),
                                              num,
            ))
            if tsl:
                approxend = tsl[-1]
                self.fields['confirm'].help_text = "Confirm that you want to generate all the tweets for this campaign at this time. Campaign will go on until approximately {}, with {} posts.".format(approxend, num)
            else:
                self.fields['confirm'].help_text = "Campaign matches no entries. Try again."

    def clean_confirm(self):
        if not self.cleaned_data['confirm']:
            if self.get_queryset().count == 0:
                del self.fields['confirm']
            else:
                raise ValidationError("Please check thix box to confirm that you want to generate all tweets!")

    def clean(self):
        if self.get_queryset().count() == 0:
            self.add_error(None, 'Current filters return no entries. Fix your filters and try again!')
            del self.fields['confirm']
        return self.cleaned_data


class ApprovedSessionsCampaignForm(BaseCampaignForm):
    tracks = forms.ModelMultipleChoiceField(required=True, queryset=Track.objects.all())

    custom_fields = ['tracks', ]

    def __init__(self, *args, **kwargs):
        super(ApprovedSessionsCampaignForm, self).__init__(*args, **kwargs)
        self.fields['tracks'].queryset = Track.objects.filter(conference=self.conference)

    @classmethod
    def generate_tweet(cls, conference, session, s):
        return render_sandboxed_template(s, {
            'conference': conference,
            'session': session,
        }).strip()[:249]

    def get_queryset(self):
        return ConferenceSession.objects.filter(conference=self.conference, status=1, cross_schedule=False, track__in=self.data.getlist('tracks'))

    def generate_tweets(self, author):
        sessions = list(self.get_queryset().order_by('?'))
        for ts, session in zip(_timestamps_for_tweets(self.conference, self.cleaned_data['starttime'], self.cleaned_data['timebetween'], self.cleaned_data['timerandom'], len(sessions)), sessions):
            ConferenceTweetQueue(
                conference=self.conference,
                datetime=ts,
                contents=self.generate_tweet(self.conference, session, self.cleaned_data['content_template']),
                approved=False,
                author=author,
            ).save()


class ApprovedSessionsCampaign(object):
    name = "Approved sessions campaign"
    form = ApprovedSessionsCampaignForm
    note = "This campaign will create one tweet for each approved session in the system."

    @classmethod
    def get_dynamic_preview(self, conference, fieldname, s):
        if fieldname == 'content_template':
            # Generate a preview of 3 (an arbitrary number) sessions
            return HttpResponse("\n\n-------------------------------\n\n".join([
                self.form.generate_tweet(conference, session, s)
                for session in ConferenceSession.objects.filter(conference=conference, status=1, cross_schedule=False)[:3]
            ]), content_type='text/plain')


allcampaigns = (
    (1, ApprovedSessionsCampaign),
)


def get_campaign_from_id(id):
    for i, c in allcampaigns:
        if i == int(id):
            return c
    raise Http404()
