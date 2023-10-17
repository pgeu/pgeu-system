from django import forms
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.utils.dateparse import parse_datetime, parse_duration
from django.utils import timezone

from postgresqleu.util.widgets import MonospaceTextarea
from postgresqleu.confreg.models import ConferenceSession, Track
from postgresqleu.confreg.models import MessagingProvider
from postgresqleu.confreg.twitter import post_conference_social, render_multiprovider_tweet
from postgresqleu.util.messaging import get_messaging, get_messaging_class
from postgresqleu.util.messaging.util import get_shortened_post_length

import datetime
import random


def _timestamps_for_tweets(conference, starttime, interval, randint, num):
    if isinstance(starttime, datetime.datetime):
        t = starttime
    else:
        t = parse_datetime(starttime)
    if not timezone.is_aware(t):
        t = timezone.make_aware(t, conference.tzobj)

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
            # Past the end of the day, so move it to the start time the next day
            t = timezone.make_aware(
                datetime.datetime.combine(t + datetime.timedelta(days=1), conference.twitter_timewindow_start),
                conference.tzobj,
            )


class BaseCampaignForm(forms.Form):
    starttime = forms.DateTimeField(label="Date and time of first tweet", initial=timezone.now)
    timebetween = forms.TimeField(label="Time between tweets", initial=datetime.time(6, 0, 0))
    timerandom = forms.TimeField(label="Time randomization", initial=datetime.time(0, 30, 0),
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
        return render_multiprovider_tweet(conference, s, {
            'conference': conference,
            'session': session,
        })

    def get_queryset(self):
        return ConferenceSession.objects.filter(conference=self.conference, status=1, cross_schedule=False, track__in=self.data.getlist('tracks'))

    def generate_tweets(self, author):
        sessions = list(self.get_queryset().order_by('?'))
        for ts, session in zip(_timestamps_for_tweets(self.conference, self.cleaned_data['starttime'], self.cleaned_data['timebetween'], self.cleaned_data['timerandom'], len(sessions)), sessions):
            post_conference_social(self.conference,
                                   self.generate_tweet(self.conference, session, self.cleaned_data['content_template']),
                                   approved=False,
                                   posttime=ts,
                                   author=author)


class BaseCampaign(object):
    @classmethod
    def get_dynamic_preview(self, conference, fieldname, templatestring):
        messagingset = [(mess.provider, get_messaging(mess.provider)) for mess in conference.conferencemessaging_set.select_related('provider').filter(broadcast=True, provider__active=True)]

        maxlens = {provider.internalname: mess.max_post_length for provider, mess in messagingset}

        if fieldname == 'content_template':
            posts = self.get_posts(conference, templatestring)
            # Calculate the longest once for each messaging provider
            longest = {}
            for provider, mess in messagingset:
                if provider.internalname not in maxlens:
                    maxlens[provider.internalname] = mess.max_post_length
                if posts:
                    longest[provider.internalname] = max((get_shortened_post_length(
                        p.get(str(provider.id), '') if isinstance(p, dict) else p
                    )) for p in posts)
                else:
                    longest[provider.internalname] = 0

            def _post_preview(p):
                val = random.choice(list(p.values())) if isinstance(p, dict) else p
                length = get_shortened_post_length(val)
                return val, length

            previews = "\n\n".join([
                "{}\n------------------------------- (length {})".format(*_post_preview(p))
                for p in posts[:5]
            ])
            return HttpResponse("{}\n\nLongest posts:\n{}\n".format(
                previews,
                "\n".join('{}: {}/{}'.format(k, longest[k], maxlens[k]) for k in sorted(maxlens.keys())),
            ), content_type='text/plain')


class ApprovedSessionsCampaign(BaseCampaign):
    name = "Approved sessions campaign"
    form = ApprovedSessionsCampaignForm
    note = "This campaign will create one tweet for each approved session in the system."

    @classmethod
    def get_posts(cls, conference, templatestring):
        return [cls.form.generate_tweet(conference, session, templatestring) for session in ConferenceSession.objects.filter(conference=conference, status=1, cross_schedule=False)]


allcampaigns = (
    (1, ApprovedSessionsCampaign),
)


def get_campaign_from_id(id):
    for i, c in allcampaigns:
        if i == int(id):
            return c
    raise Http404()
