from django import forms
from django.shortcuts import render
from django.core.validators import ValidationError
from django.db import transaction

import base64
import json

from postgresqleu.confreg.util import get_authenticated_conference
from postgresqleu.util.widgets import StaticTextWidget
from postgresqleu.confreg.models import ConferenceSession


class UploadTypes:
    def __init__(self):
        self.types = {}

    def register(self, cls):
        self.types[cls.__name__] = cls

    def get(self, name):
        return self.types[name]

    @property
    def choices(self):
        yield ('', '-- Select type of file to upload --')
        for k, v in self.types.items():
            yield k, v.name


uploadtypes = UploadTypes()


class BaseUploadType:
    def __init__(self, conference, content):
        self.conference = conference
        self.content = content

    def validate(self):
        try:
            self.decoded = json.loads(self.content)
        except json.decoder.JSONDecodeError:
            raise ValidationError('Could not parse JSON')


class VideoLinks(BaseUploadType):
    name = 'Video links'

    def validate(self):
        super().validate()
        providers = self.conference.videoproviders.split(',')

        if 'sessions' not in self.decoded:
            raise ValidationError('Root key "sessions" does not exist')
        if not isinstance(self.decoded['sessions'], dict):
            raise ValidationError('"sessions" is not a dict')
        for k, v in self.decoded['sessions'].items():
            try:
                int(k)
            except ValueError:
                raise ValidationError('Session id {} is not an integer'.format(k))
            if not isinstance(v, dict):
                raise ValidationError('Video data for session {} is not a dict'.format(k))
            for kk, vv in v.items():
                if kk not in providers:
                    raise ValidationError('Unknown video type "{}" for session {}. Is it enabled for this conference?'.format(kk, k))
        num = len(self.decoded['sessions'])
        found = self.conference.conferencesession_set.filter(id__in=self.decoded['sessions'].keys()).count()
        previous = self.conference.conferencesession_set.exclude(videolinks={}).exclude(id__in=self.decoded['sessions'].keys()).count()
        return 'Loaded videos for {} sessions, {} were found and {} were not found and will be ignored.<br/>{} sessions already had videos but are not included in the import, and will not be overwritten.'.format(
            num,
            found,
            num - found,
            previous,
        )

    def execute(self):
        for k, v in self.decoded['sessions'].items():
            try:
                s = ConferenceSession.objects.only('id', 'title', 'videolinks').get(pk=k, conference=self.conference)
                for kk, vv in v.items():
                    if s.videolinks.get(kk, None) != vv:
                        s.videolinks[kk] = vv
                        s.save(update_fields=['videolinks'])
                        yield 'Set {} on {} ({}) to {}'.format(kk, s.id, s.title, vv)
                    else:
                        yield 'Unmodified video {} ({}).'.format(k, s.title)
            except ConferenceSession.DoesNotExist:
                yield 'Could not find session {} for this conference.'.format(k)


uploadtypes.register(VideoLinks)


class UploadForm(forms.Form):
    resourcetype = forms.ChoiceField(choices=uploadtypes.choices, label='Type', required=False)
    f = forms.FileField(label='File', required=False, help_text='File to upload (JSON format)')
    data = forms.CharField(widget=forms.HiddenInput, required=False)
    status = forms.CharField(widget=StaticTextWidget, required=False)

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference
        self.statusstring = None
        self.persistentdata = None
        super().__init__(*args, **kwargs)

        if 'data' not in kwargs:
            self.stage = 0
        elif kwargs['data'].get('submit', None) == 'Upload file':
            self.stage = 1
        else:
            self.stage = 2

        self.fields['f'].widget.attrs['accept'] = 'application/json'

    def remove_fields(self):
        if self.stage == 0:
            del self.fields['status']
        else:
            del self.fields['resourcetype']
            del self.fields['f']

    def clean(self):
        data = super().clean()

        if self.stage == 1:
            if not data.get('resourcetype', None):
                self.add_error('resourcetype', 'This field is required')
                return data
            if not data.get('f', None):
                self.add_error('f', 'A file must be uploaded')
                return data
            uploadtype = uploadtypes.get(data['resourcetype'])
            filedata = data['f'].read()
        else:
            try:
                j = json.loads(base64.b64decode(data['data']))
            except Exception:
                self.add_error('status', "Failed to parse presisted data, please start over.")
            uploadtype = uploadtypes.get(j['resourcetype'])
            data['resourcetype'] = j['resourcetype']
            filedata = j['data'].encode()

        if uploadtype is None:
            self.add_error('resourcetype', 'Could not find resource type')
            return data

        self.upload_processor = uploadtype(self.conference, filedata)
        try:
            self.statusstring = self.upload_processor.validate()
        except ValidationError as e:
            self.add_error('f', e)
            return data

        self.persistentdata = base64.b64encode(json.dumps({
            'resourcetype': data['resourcetype'],
            'data': filedata.decode(),
        }).encode()).decode()

        return data

    def execute(self):
        return self.upload_processor.execute()


def index(request, confname):
    conference = get_authenticated_conference(request, confname)

    if request.method == 'POST':
        form = UploadForm(conference, data=request.POST, files=request.FILES)
        if form.is_valid():
            if form.stage == 1:
                # Ugly way, but it works. I think
                form.data = {**form.data.dict(), 'status': form.statusstring, 'data': form.persistentdata}
            else:
                with transaction.atomic():
                    results = form.execute()
                    return render(request, 'confreg/file_upload_results.html', {
                        'conference': conference,
                        'results': list(results),
                        'breadcrumbs': [
                            ('./', 'Upload file'),
                        ],
                        'helplink': 'upload',
                    })
        else:
            form.stage = 0
    else:
        form = UploadForm(conference)

    form.remove_fields()
    return render(request, 'confreg/admin_backend_form.html', {
        'conference': conference,
        'conference': conference,
        'basetemplate': 'confreg/confadmin_base.html',
        'form': form,
        'savebutton': 'Upload file' if form.stage == 0 else 'Confirm and upload file',
        'cancelurl': '.' if form.stage > 0 else None,
        'whatverb': 'Upload',
        'what': 'file',
        'helplink': 'upload',
    })
