from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible

from StringIO import StringIO

import requests
from PIL import Image

def validate_lowercase(value):
	if value != value.lower():
		raise ValidationError("This field must be lowercase only")


class BeforeValidator(object):
	def __init__(self, beforedate):
		self.beforedate = beforedate

	def __call__(self, value):
		if value >= self.beforedate:
			raise ValidationError("Ensure this date is before {0}".format(self.beforedate))

class AfterValidator(object):
	def __init__(self, afterdate):
		self.afterdate = afterdate

	def __call__(self, value):
		if value <= self.afterdate:
			raise ValidationError("Ensure this date is after {0}".format(self.afterdate))


def TwitterValidator(value):
	if value.startswith('@'):
		value = value[1:]

	if value == '':
		# This can only happen if it was '@' initially
		raise ValidationError("Enter twitter name or leave field empty")

	try:
		r = requests.head('https://twitter.com/{0}'.format(value),
						  headers={'User-agent': 'Firefox/60'},
						  timeout=5)
	except requests.exceptions.ReadTimeout:
		raise ValidationError("Could not verify twitter name - timeout")

	if r.status_code != 200:
		raise ValidationError("Could not verify twitter name: {0}".format(r.status_code))

	# All is well! :)


def validate_json_structure(config, structure):
	def _validate_json_level(config, structure, path):
		missing = set(structure.keys()).difference(set(config.keys()))
		if missing:
			raise ValidationError("Keys {0} are missing".format(", ".join(["->".join(path+[m]) for m in missing])))
		extra = set(config.keys()).difference(set(structure.keys()))
		if extra:
			raise ValidationError("Keys {0} are not allowed".format(", ".join(["->".join(path+[m]) for m in extra])))

		# Keys are correct, validate datatypes
		for k,v in config.items():
			fullkey = "->".join(path+[k])
			# Dicts don't have __name__
			if type(structure[k]) == dict:
				structtype = dict
			else:
				structtype = structure[k]
			structname = structtype.__name__
			valname = type(v).__name__

			if type(v) != structtype:
				raise ValidationError("Value for {0} should be of type {1}, not {2}".format(fullkey, structname, valname))
			if isinstance(v, dict):
				# Recursively check substructure
				_validate_json_level(v, structure[k], path+[k])

	_validate_json_level(config, structure, [])


@deconstructible
class PictureUrlValidator(object):
	def __init__(self, aspect=None):
		self.aspect = aspect

	def __call__(self, value):
		try:
			r = requests.get(value,
							 headers={'User-agent': 'Firefox/60'},
							 timeout=5)
		except:
			raise ValidationError("Could not download promotion picture")

		if r.status_code != 200:
			raise ValidationError("Downloading promo picture returned status %s" % r.status_code)
		try:
			img = Image.open(StringIO(r.content))
			w,h = img.size
			if self.aspect:
				newaspect = round(float(w)/float(h), 2)
				if newaspect != self.aspect:
					raise ValidationError("Image has aspect ratio %s, must have %s" % (newaspect, self.aspect))

		except ValidationError:
			raise
		except Exception, e:
			raise ValidationError("Failed to parse image: %s" % e)

	def __eq__(self, other):
		return self.aspect == other.aspect
