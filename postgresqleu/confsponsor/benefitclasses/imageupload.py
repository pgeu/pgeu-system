from django import forms
from django.core.exceptions import ValidationError
from django.http import HttpResponse

import base64
import io
from PIL import ImageFile

from postgresqleu.util.storage import InlineEncodedStorage
from postgresqleu.util.forms import IntegerBooleanField
from postgresqleu.util.widgets import StaticTextWidget
from postgresqleu.util.validators import color_validator
from postgresqleu.confsponsor.backendforms import BackendSponsorshipLevelBenefitForm

from .base import BaseBenefit, BaseBenefitForm


class ImageUploadForm(BaseBenefitForm):
    decline = forms.BooleanField(label='Decline this benefit', required=False)
    image = forms.FileField(label='Image file', required=False)
    uploadedimage = forms.CharField(label='Uploaed', widget=forms.HiddenInput, required=False)
    preview = forms.CharField(label='Preview', required=False, widget=StaticTextWidget)
    confirm = forms.BooleanField(label='Confirm preview', required=False)

    def __init__(self, *args, **kwargs):
        super(ImageUploadForm, self).__init__(*args, **kwargs)

        self.fields['image'].help_text = "Upload a file in %s format, fitting in a box of %sx%s pixels." % (self.params['format'].upper(), self.params['xres'], self.params['yres'])
        self.fields['image'].widget.attrs['accept'] = 'image/png'

        if not self.is_bound:
            self._delete_stage2_fields()

    def _delete_stage2_fields(self):
        del self.fields['uploadedimage']
        del self.fields['preview']
        del self.fields['confirm']

    def clean(self):
        declined = self.cleaned_data.get('decline', False)
        if declined and self.cleaned_data.get('image', None):
            self._delete_stage2_fields()
            raise ValidationError('You cannot both decline and upload an image at the same time.')

        if declined:
            self._delete_stage2_fields()
        else:
            if self.cleaned_data.get('image', None) or self.cleaned_data.get('uploadedimage', None):
                # We have an image. Prepare a preview field if it's not already confirmed
                self.data = self.data.copy()
                if self.cleaned_data.get('image', None):
                    self.cleaned_data['image'].seek(0)
                    imgdata = base64.b64encode(self.cleaned_data['image'].read()).decode('ascii')
                    imgtag = "data:image/png;base64,{}".format(imgdata)
                    self.data['uploadedimage'] = imgdata
                else:
                    imgtag = "data:image/png;base64,{}".format(self.cleaned_data['uploadedimage'])

                if self.params.get('previewbackground', None):
                    self.data['preview'] = '<div class="sponsor-imagepreview"><span>Uploaded image: </span><img src="{}" /></div><div class="sponsor-imagepreview"><span>Preview on background: </span><img src="{}" style="background-color: {}" /></div>'.format(imgtag, imgtag, self.params.get('previewbackground'))
                else:
                    self.data['preview'] = '<div class="sponsor-imagepreview"><span>Uploaded image: </span><img src="{}" /></div><div class="sponsor-imagepreview"></div>'.format(imgtag)

                # Remove the image field now that we have transferred things to imagedata. Also remove the ability to decline.
                del self.fields['image']
                del self.fields['decline']

                # And finally, check if we've already confirmed
                if not self.cleaned_data.get('confirm', None):
                    self.add_error('confirm', "You must confirm the image looks OK in the preview before you can proceed.{}".format(
                        ' In particular, verify the effect of transparency on the given background color.' if self.params.get('previewbackground') else '',
                    ))
            else:
                # If we don't have an image it either wasn't specified, or the image validator removed it
                if 'image' not in self._errors:
                    # Unless there is an error already flagged in the clean_image method
                    self._errors['image'] = self.error_class(['This field is required'])

                self._delete_stage2_fields()

        return self.cleaned_data

    def clean_image(self):
        if not self.cleaned_data.get('image', None):
            # This check is done in the global clean as well, so we accept it here since
            # we might have decliend it.
            return None

        imagedata = self.cleaned_data['image']
        try:
            p = ImageFile.Parser()
            p.feed(imagedata.read())
            p.close()
            image = p.image
        except Exception as e:
            raise ValidationError("Could not parse image: %s" % e)
        if image.format != self.params['format'].upper():
            raise ValidationError("Only %s format images are accepted, not '%s'" % (self.params['format'].upper(), image.format))
        xres = int(self.params['xres'])
        yres = int(self.params['yres'])
        resstr = "%sx%s" % (xres, yres)
        upresstr = "%sx%s" % image.size
        # Check maximum resolution
        if image.size[0] > xres or image.size[1] > yres:
            raise ValidationError("Maximum size of image is %s. Uploaded image is %s." % (resstr, upresstr))
        # One of the sizes has to be exactly what the spec says, otherwise we might have an image that's
        # too small.
        if image.size[0] != xres and image.size[1] != yres:
            raise ValidationError("Image must be %s pixels wide or %s pixels high. Uploaded image is %s." % (xres, yres, upresstr))

        if int(self.params.get('transparent', 0)) == 1:
            # Require transparency, only supported for PNG
            if self.params['format'].upper() != 'PNG':
                raise ValidationError("Transparency validation requires PNG images")
            if image.mode != 'RGBA':
                raise ValidationError("Image must have transparent background")

        return self.cleaned_data['image']


class ImageUploadBackendForm(BackendSponsorshipLevelBenefitForm):
    format = forms.ChoiceField(label="Image format", choices=(('PNG', 'PNG'), ))
    xres = forms.IntegerField(label="X resolution")
    yres = forms.IntegerField(label="Y resolution")
    transparent = IntegerBooleanField(label="Require transparent", required=False)
    previewbackground = forms.CharField(max_length=20, required=False,
                                        label='Preview background',
                                        validators=[color_validator, ],
                                        help_text="Background color used in preview",
                                        )

    class_param_fields = ['format', 'xres', 'yres', 'transparent', 'previewbackground']


class ImageUpload(BaseBenefit):
    @classmethod
    def get_backend_form(self):
        return ImageUploadBackendForm

    def generate_form(self):
        return ImageUploadForm

    def save_form(self, form, claim, request):
        if form.cleaned_data['decline']:
            return False
        storage = InlineEncodedStorage('benefit_image')
        storage.save(str(claim.id), io.BytesIO(base64.b64decode(form.cleaned_data['uploadedimage'])))
        return True

    def render_claimdata(self, claimedbenefit, isadmin):
        if claimedbenefit.declined:
            return 'Benefit declined.'

        if self.params.get('previewbackground', None):
            return '<div class="sponsor-imagepreview"><span>Uploaded image: </span><img src="/events/sponsor/admin/imageview/{}/" /></div><div class="sponsor-imagepreview"><span>Preview on background: </span><img src="/events/sponsor/admin/imageview/{}/" style="background-color: {}" /></div>'.format(claimedbenefit.id, claimedbenefit.id, self.params.get('previewbackground'))
        return 'Uploaded image: <img src="/events/sponsor/admin/imageview/%s/" />' % claimedbenefit.id

    def get_claimdata(self, claimedbenefit):
        return {
            'image': {
                'suburl': '/{}'.format(claimedbenefit.id),
                'tag': InlineEncodedStorage('benefit_image').get_tag(claimedbenefit.id),
            },
        }

    def get_claimfile(self, claimedbenefit):
        hashval, data, metadata = InlineEncodedStorage('benefit_image').read(claimedbenefit.id)
        if hashval is None and data is None:
            raise Http404()
        resp = HttpResponse(content_type='image/png')
        resp['ETag'] = '"{}"'.format(hashval)
        resp.write(data)
        return resp

    def delete_claimed_benefit(self, claim):
        InlineEncodedStorage('benefit_image').delete(claim.id)
        super().delete_claimed_benefit(claim)
