from django import forms
from django.core.exceptions import ValidationError

import simplejson
from PIL import ImageFile

from postgresqleu.util.storage import InlineEncodedStorage

from base import BaseBenefit

def _validate_params(params):
	try:
		j = simplejson.loads(params)
		if sorted(j.keys()) != [u"format", u"xres", u"yres"]:
			raise Exception("Parameters 'format', 'xres' and 'yres' are mandatory")
		if int(j['xres']) < 1:
			raise Exception("Parameter 'xres' must be positive integer!")
		if int(j['yres']) < 1:
			raise Exception("Parameter 'yres' must be positive integer!")

		return j
	except simplejson.JSONDecodeError:
		raise Exception("Can't parse JSON")

class ImageUploadForm(forms.Form):
	decline = forms.BooleanField(label='Decline this benefit', required=False)
	image = forms.FileField(label='Image file', required=False)

	def __init__(self, benefit, *args, **kwargs):
		self.params = _validate_params(benefit.class_parameters)

		super(ImageUploadForm, self).__init__(*args, **kwargs)

		self.fields['image'].help_text = "Upload a file in %s format, fitting in a box of %sx%s pixels." % (self.params['format'].upper(), self.params['xres'], self.params['yres'])

	def clean(self):
		declined = self.cleaned_data.get('decline', False)
		if not declined:
			if not self.cleaned_data.get('image', None):
				if not self._errors.has_key('image'):
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
		except Exception, e:
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
			raise ValidationError("Image must be %s pixels wide or %s pixels high, fitting within a box of %s. Uploaded image is %s." % (xres, yres, resstr, upresstr))

		# XXX: future improvement: support transparency check

		return self.cleaned_data['image']

class ImageUpload(BaseBenefit):
	description = 'Require uploaded image'
	default_params = '{"format": "png", "xres": 1, "yres": 1}'
	def validate_params(self):
		try:
			_validate_params(self.params)
		except Exception, e:
			return e

	def generate_form(self):
		return ImageUploadForm

	def save_form(self, form, claim, request):
		if form.cleaned_data['decline']:
			claim.declined=True
			claim.confirmed=True
			return True
		storage = InlineEncodedStorage('benefit_image')
		storage.save(str(claim.id), form.cleaned_data['image'])
		return True

	def render_claimdata(self, claimedbenefit):
		# We don't use the datafield, just the id
		return 'Uploaded image: <img src="/events/sponsor/admin/imageview/%s/" />' % claimedbenefit.id

