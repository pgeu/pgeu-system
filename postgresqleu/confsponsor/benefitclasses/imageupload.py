from django import forms
from django.core.exceptions import ValidationError

from PIL import ImageFile

from postgresqleu.util.storage import InlineEncodedStorage
from postgresqleu.util.forms import IntegerBooleanField
from postgresqleu.confsponsor.backendforms import BackendSponsorshipLevelBenefitForm

from .base import BaseBenefit, BaseBenefitForm


class ImageUploadForm(BaseBenefitForm):
    decline = forms.BooleanField(label='Decline this benefit', required=False)
    image = forms.FileField(label='Image file', required=False)

    def __init__(self, *args, **kwargs):
        super(ImageUploadForm, self).__init__(*args, **kwargs)

        self.fields['image'].help_text = "Upload a file in %s format, fitting in a box of %sx%s pixels." % (self.params['format'].upper(), self.params['xres'], self.params['yres'])
        self.fields['image'].widget.attrs['accept'] = 'image/png'

    def clean(self):
        declined = self.cleaned_data.get('decline', False)
        if not declined:
            if not self.cleaned_data.get('image', None):
                if 'image' not in self._errors:
                    # Unless there is an error already flagged in the clean_image method
                    self._errors['image'] = self.error_class(['This field is required'])
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

    class_param_fields = ['format', 'xres', 'yres', 'transparent']


class ImageUpload(BaseBenefit):
    @classmethod
    def get_backend_form(self):
        return ImageUploadBackendForm

    def generate_form(self):
        return ImageUploadForm

    def save_form(self, form, claim, request):
        if form.cleaned_data['decline']:
            claim.declined = True
            claim.confirmed = True
            return True
        storage = InlineEncodedStorage('benefit_image')
        storage.save(str(claim.id), form.cleaned_data['image'])
        return True

    def render_claimdata(self, claimedbenefit, isadmin):
        # We don't use the datafield, just the id
        return 'Uploaded image: <img src="/events/sponsor/admin/imageview/%s/" />' % claimedbenefit.id
