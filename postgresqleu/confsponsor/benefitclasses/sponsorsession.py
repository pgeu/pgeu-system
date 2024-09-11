from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction

import base64

from PIL import ImageFile

from postgresqleu.confsponsor.backendforms import BackendSponsorshipLevelBenefitForm
from postgresqleu.confsponsor.benefitclasses.base import BaseBenefit, BaseBenefitForm
from postgresqleu.confreg.models import ConferenceSession, Track, Speaker
from postgresqleu.confreg.models import PRIMARY_SPEAKER_PHOTO_RESOLUTION
from postgresqleu.util.image import rescale_image
from postgresqleu.util.random import generate_random_token


class SponsorSessionForm(BaseBenefitForm):
    decline = forms.BooleanField(label='Decline this benefit', required=False)
    title = forms.CharField(label="Title", min_length=10, max_length=200, required=False)
    abstract = forms.CharField(label="Abstract", min_length=30, max_length=1000, required=False, widget=forms.Textarea())
    speakername = forms.CharField(label="Speaker name", max_length=100, required=False)
    speakercompany = forms.CharField(label="Speaker company", max_length=100, required=False)
    speakerbio = forms.CharField(label="Speaker bio", max_length=1000, required=False, widget=forms.Textarea())
    speakerphoto = forms.FileField(label="Speaker photo", required=False, help_text="Photo will be rescaled to {}x{} pixels. We reserve the right to make minor edits to speaker photos if necessary".format(*PRIMARY_SPEAKER_PHOTO_RESOLUTION))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['speakercompany'].initial = self.sponsor.displayname

    def clean(self):
        declined = self.cleaned_data.get('decline', False)
        if declined:
            if self.cleaned_data.get('title', ''):
                self.add_error('title', "Don't specify a title when declining the benefit")
            if self.cleaned_data.get('abstract', ''):
                self.add_error('abstract', "Don't specify an abstract when declining the benefit")
            if self.cleaned_data.get('speakername', ''):
                self.add_error('speakername', "Don't specify a speaker name when declining the benefit")
            if self.cleaned_data.get('speakercompany', ''):
                self.add_error('speakercompany', "Don't specify a speaker company when declining the benefit")
            if self.cleaned_data.get('speakerbio', ''):
                self.add_error('speakerbio', "Don't specify a speaker bio when declining the benefit")
        else:
            if not self.cleaned_data.get('title', ''):
                self.add_error('title', 'Title must be specified unless benefit is declined.')
            if not self.cleaned_data.get('abstract', ''):
                self.add_error('abstract', 'Abstract must be specified unless benefit is declined.')
            if not self.cleaned_data.get('speakername', ''):
                self.add_error('speakername', 'Speaker name must be specified unless benefit is declined.')
            if not self.cleaned_data.get('speakerbio', ''):
                self.add_error('speakerbio', 'Speaker bio must be specified unless benefit is declined.')
        return self.cleaned_data

    def clean_image(self):
        if not self.cleaned_data.get('speakerphoto', None):
            # This check is done in the global clean as well, so we accept it here since
            # we might have decliend it.
            return None

        imagedata = self.cleaned_data['speakerphoto']
        try:
            p = ImageFile.Parser()
            p.feed(imagedata.read())
            p.close()
            image = p.image
        except Exception as e:
            raise ValidationError("Could not parse image: %s" % e)

        if image.format not in ['JPEG', 'PNG']:
            raise ValidationError("Photo must be JPEG or PNG format")

        return self.cleaned_data['speakerphoto']


class SponsorSessionBackendForm(BackendSponsorshipLevelBenefitForm):
    track = forms.ChoiceField(label='Track', choices=[], required=True)
    htmlicon = forms.CharField(label='HTML icon', max_length=100, help_text='Assign HTML icon to submitted sessions', required=False)

    class_param_fields = ['track', 'htmlicon', ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['track'].choices = [(t.id, t.trackname) for t in Track.objects.filter(conference=self.conference)]


class SponsorSession(BaseBenefit):
    @classmethod
    def get_backend_form(self):
        return SponsorSessionBackendForm

    def generate_form(self):
        return SponsorSessionForm

    def save_form(self, form, claim, request):
        if form.cleaned_data['decline']:
            return False

        for f in ['title', 'abstract', 'speakername', 'speakercompany', 'speakerbio']:
            claim.claimjson[f] = form.cleaned_data[f]

        if form.cleaned_data.get('speakerphoto', None):
            # There is an image, so rescale and add it
            p = ImageFile.Parser()
            imgdata = form.cleaned_data['speakerphoto'].read()
            p.feed(imgdata)
            p.close()
            img = p.image
            if img.size[0] != PRIMARY_SPEAKER_PHOTO_RESOLUTION[0] or img.size[1] != PRIMARY_SPEAKER_PHOTO_RESOLUTION[1]:
                claim.claimjson['photo'] = base64.b64encode(rescale_image(img, PRIMARY_SPEAKER_PHOTO_RESOLUTION, centered=True)).decode()
            else:
                claim.claimjson['photo'] = base64.b64encode(imgdata).decode()

        return True

    def render_claimdata(self, claimedbenefit, isadmin):
        if claimedbenefit.declined:
            return ""

        s = """
<strong>Title:</strong> {}<br/>
<strong>Abstract:</strong> {}<br/>
<strong>Speaker:</strong> {}<br/>
<strong>Company:</strong> {}<br/>
<strong>Bio:</strong> {}<br/>
""".format(
            claimedbenefit.claimjson['title'],
            claimedbenefit.claimjson['abstract'],
            claimedbenefit.claimjson['speakername'],
            claimedbenefit.claimjson['speakercompany'],
            claimedbenefit.claimjson['speakerbio'],
        )

        if 'photo' in claimedbenefit.claimjson:
            s += '<strong>Photo:</strong><br/><img style="border: 1px solid black;" src="data:{};base64,{}">'.format(
                'image/png' if claimedbenefit.claimjson['photo'][:11] == 'iVBORw0KGgo' else 'image/jpg',  # base64 encoded version of magic png header
                claimedbenefit.claimjson['photo'],
            )

        if isadmin and 'session' in claimedbenefit.claimjson:
            return '<a href="/events/admin/{}/sessions/{}/">Session</a> and <a href="/events/admin/{}/speakers/{}/">speaker</a> record for this claim were created when it was confirmed.<br/>The below data contains the original submission.<br/><br/>'.format(
                self.level.conference.urlname,
                claimedbenefit.claimjson['session'],
                self.level.conference.urlname,
                claimedbenefit.claimjson['speaker'],
            ) + s
        return s

    def get_claimdata(self, claimedbenefit):
        d = {
            'title': claimedbenefit.claimjson['title'],
            'abstract': claimedbenefit.claimjson['abstract'],
            'speaker': {
                'name': claimedbenefit.claimjson['speakername'],
                'company': claimedbenefit.claimjson['speakercompany'],
                'bio': claimedbenefit.claimjson['speakerbio'],
            },
        }
        if 'session' in claimedbenefit.claimjson:
            d['sessionid'] = claimedbenefit.claimjson['session']
            d['speaker']['speakerid'] = claimedbenefit.claimjson['speaker']
        return d

    def render_reportinfo(self, claimedbenefit):
        if 'session' in claimedbenefit.claimjson:
            session = speaker = ""
            try:
                session = ConferenceSession.objects.get(pk=claimedbenefit.claimjson['session']).title
                speaker = Speaker.objects.get(pk=claimedbenefit.claimjson['speaker']).fullname
            except Exception:
                pass
            return '{} by {}'.format(session, speaker)
        else:
            return ''

    def can_unclaim(self, claimedbenefit):
        # We allow unclaiming even of approved sessions, and we'll just go delete them.
        return True

    def process_unclaim(self, claimedbenefit):
        if 'session' in claimedbenefit.claimjson:
            with transaction.atomic():
                speaker = Speaker.objects.get(pk=claimedbenefit.claimjson['speaker'])
                if not speaker.conferencesession_set.exclude(pk=claimedbenefit.claimjson['session']).exists():
                    # This speaker has no other sessions, so delete it
                    speaker.delete()

                # Session exists, so we must delete it.
                ConferenceSession.objects.get(pk=claimedbenefit.claimjson['session']).delete()

    def validate_parameters(self):
        # Verify that the track being copied in actually exists
        if not Track.objects.filter(conference=self.level.conference, pk=self.params['track']).exists():
            raise ValidationError("Track id {} does not exist".format(self.params['track']))

    def transform_parameters(self, oldconference, newconference):
        # Match the track on name instead of id!
        if 'track' in self.params:
            # Should always exist, but it's up to validation to make sure it does
            try:
                oldtrack = Track.objects.get(conference=oldconference, pk=self.params['track'])
            except Track.DoesNotExist:
                raise ValidationError("Could not find track name in old conference")
            try:
                self.params['track'] = Track.objects.get(conference=newconference, trackname=oldtrack.trackname).pk
            except Track.DoesNotExist:
                raise ValidationError("Track '{}' does not exist".format(oldtrack.trackname))

    def process_confirm(self, claim):
        # When confirmed we populate a speaker and a session record
        speaker = Speaker(
            fullname=claim.claimjson['speakername'],
            company=claim.claimjson['speakercompany'],
            abstract=claim.claimjson['speakerbio'],
            speakertoken=generate_random_token(),
            attributes={
                'source': 'sponsor',
                'sponsor': {
                    'id': claim.sponsor.id,
                    'name': claim.sponsor.displayname,
                },
                'benefit': {
                    'claimid': claim.id,
                    'benefit': claim.benefit.benefitname,
                }
            }
        )
        if 'photo' in claim.claimjson:
            speaker.photo512 = base64.b64decode(claim.claimjson['photo'].encode())
        speaker.save()

        session = ConferenceSession(
            conference=self.level.conference,
            title=claim.claimjson['title'],
            track=Track.objects.get(conference=self.level.conference, id=self.params['track']),
            abstract=claim.claimjson['abstract'],
            htmlicon=self.params['htmlicon'],
            status=1,                  # Default to fully confirmed, since we can't ask the speaker for confirmation here!
            lastnotifiedstatus=1,      # Default to fully confirmed, since we don't have an email to send notifications to anyway
            submissionnote='Submitted as sponsor benefit for {}'.format(claim.sponsor.name),
            internalnote='Submitted by sponsor {}. benefit {}, claim id {}'.format(claim.sponsor.name, claim.benefit.benefitname, claim.id),
        )
        session.save()

        session.speaker.set([speaker])

        # Store the session id and speaker id on our claim
        claim.claimjson['session'] = session.id
        claim.claimjson['speaker'] = speaker.id

        # Delete the photo, to keep the size down
        if 'photo' in claim.claimjson:
            del claim.claimjson['photo']

        # Send the regular notification that the benefit is confirmed
        return True
