from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.http import HttpResponse
from django.conf import settings

import base64
import io
import zipfile

from postgresqleu.util.storage import InlineEncodedStorage
from postgresqleu.util.forms import IntegerBooleanField
from postgresqleu.util.widgets import StaticTextWidget
from postgresqleu.util.validators import color_validator
from postgresqleu.util.magic import magicdb
from postgresqleu.confsponsor.backendforms import BackendSponsorshipLevelBenefitForm

from .base import BaseBenefit, BaseBenefitForm


class FileUploadForm(BaseBenefitForm):
    decline = forms.BooleanField(label='Decline this benefit', required=False)
    file = forms.FileField(label='File', required=False)
    uploadedfile = forms.CharField(label='Uploaed', widget=forms.HiddenInput, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['file'].help_text = "Upload a file of maximum size {}KB".format(self.params['maxsize'])
        if self.params['mimetypes']:
            acceptzipstr = ',application/zip' if self.params['acceptzip'] else ''
            self.fields['file'].widget.attrs['accept'] = self.params['mimetypes'] + acceptzipstr

    def clean(self):
        if self.cleaned_data.get('decline', False) and self.cleaned_data.get('file', None):
            raise ValidationError('You cannot both decline and upload a file at the same time.')

        if not self.cleaned_data.get('file', None) and 'file' not in self._errors:
            self.add_error('file', 'A file must be uploaded')

        return self.cleaned_data

    def clean_file(self):
        if not self.cleaned_data.get('file', None):
            # This check is done in the global clean as well, so we accept it here since
            # we might have decliend it.
            return None

        filedata = self.cleaned_data['file']

        if filedata.size > self.params.get('maxsize') * 1024:
            raise ValidationError("Uploaded file is too large, maximum size is {}Kb.".format(self.params.get('maxsize')))

        def _mimetype_ok(mimetype):
            for t in self.params.get('mimetypes').split(','):
                if mimetype.startswith(t):
                    return True
            return False

        if self.params.get('mimetypes', None):
            mimetype = magicdb.buffer(filedata.read(2048))
            if self.params.get('acceptzip', False) and mimetype.startswith('application/zip'):
                filedata.seek(0)
                try:
                    with zipfile.ZipFile(filedata) as zf:
                        for fn in zf.namelist():
                            with zf.open(fn) as ff:
                                mimetype = magicdb.buffer(ff.read(2048))
                                if not _mimetype_ok(mimetype):
                                    raise ValidationError("ZIP file contains file {} which is of invalid type: {}".format(fn, mimetype))
                except zipfile.BadZipFile:
                    raise ValidationError("Could not parse uploaded ZIP file")
            elif not _mimetype_ok(mimetype):
                raise ValidationError("Invalid type of file uploaded: {}".format(mimetype))

        filedata.seek(0)

        return self.cleaned_data['file']


class FileUploadBackendForm(BackendSponsorshipLevelBenefitForm):
    maxsize = forms.IntegerField(label='Maximum size in Kb', initial=1024, validators=[MinValueValidator(10), MaxValueValidator(int(settings.DATA_UPLOAD_MAX_MEMORY_SIZE / 1024))])
    mimetypes = forms.CharField(label='MIME types', help_text='Allow only the specified MIME types, leave empty to allow all', required=False)
    acceptzip = forms.BooleanField(label='Accept zip', initial=True, help_text='Accept a ZIP version containing the above list of MIME types', required=False)

    class_param_fields = ['maxsize', 'mimetypes', 'acceptzip', ]

    def clean_mimetypes(self):
        m = self.cleaned_data['mimetypes']
        if m == '':
            return m
        parts = m.split(',')
        for p in parts:
            if ' ' in p:
                raise ValidationError('Whitespace not allowed in MIME types')
            mimeparts = p.split('/')
            if len(mimeparts) != 2:
                raise ValidationError('Each MIME type must be of format x/y')
        return m

    def clean(self):
        if self.cleaned_data.get('mimetypes', '') == '' and self.cleaned_data.get('acceptzip', False):
            self.add_error('acceptzip', 'Accept zip only makes sense when MIME type is specified')

        return self.cleaned_data


class FileUpload(BaseBenefit):
    @classmethod
    def get_backend_form(self):
        return FileUploadBackendForm

    def generate_form(self):
        return FileUploadForm

    def save_form(self, form, claim, request):
        if form.cleaned_data['decline']:
            return False
        storage = InlineEncodedStorage('benefit_file')
        storage.save(str(claim.id), form.cleaned_data['file'], {
            'filename': form.cleaned_data['file'].name,
        })
        return True

    def render_claimdata(self, claimedbenefit, isadmin):
        if claimedbenefit.declined:
            return 'Benefit declined.'

        storage = InlineEncodedStorage('benefit_file')
        fn = storage.get_metadata(claimedbenefit.id)['filename']

        if isadmin:
            return 'Uploaded file: {}. <a href="/events/sponsor/admin/downloadfile/{}/">Download</a>.'.format(
                fn,
                claimedbenefit.id,
            )
        else:
            return 'Uploaded file: {}'.format(fn)

    def get_claimdata(self, claimedbenefit):
        return {
            'filename': InlineEncodedStorage('benefit_file').get_metadata(claimedbenefit.id)['filename'],
        }

    def get_claimfile(self, claimedbenefit):
        hashval, data, metadata = InlineEncodedStorage('benefit_file').read(claimedbenefit.id)
        if hashval is None and data is None:
            raise Http404()
        resp = HttpResponse(content_type='application/octet_stream')
        resp['Content-Disposition'] = 'attachment; filename={}'.format(metadata['filename'])
        resp['ETag'] = '"{}"'.format(hashval)
        resp.write(data)
        return resp

    def delete_claimed_benefit(self, claim):
        InlineEncodedStorage('benefit_file').delete(claim.id)
        super().delete_claimed_benefit(claim)
