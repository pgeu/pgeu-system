from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator, RegexValidator
from django.utils.deconstruct import deconstructible

from io import BytesIO
import re

import requests
from PIL import Image, ImageFile


def validate_lowercase(value):
    if value != value.lower():
        raise ValidationError("This field must be lowercase only")


_urlname_re = re.compile(r'^\w+\Z')
validate_urlname = RegexValidator(
    _urlname_re,
    "Enter a valid urlname consisting of letters, numbers or underscore.",
    'invalid'
)


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


def Http200Validator(value):
    try:
        r = requests.get(value, timeout=5)
        if r.status_code != 200:
            raise ValidationError("URL must return 200 OK, not {0}".format(r.status_code))

    except requests.ConnectionError:
        raise ValidationError("Connection to server failed")
    except requests.exceptions.ReadTimeout:
        raise ValidationError("URL timed out")


def TwitterValidator(value):
    if value.startswith('@'):
        value = value[1:]

    if value == '':
        # This can only happen if it was '@' initially
        raise ValidationError("Enter twitter name or leave field empty")

    try:
        r = requests.get('https://twitter.com/{0}'.format(value),
                         headers={'User-agent': 'Firefox/60'},
                         timeout=5)
    except requests.exceptions.ReadTimeout:
        raise ValidationError("Could not verify twitter name - timeout")

    if r.status_code != 200:
        raise ValidationError("Could not verify twitter name: {0}".format(r.status_code))

    # All is well! :)


def ListOfEmailAddressValidator(value):
    for p in value.split(','):
        EmailValidator("Enter a comma separated list of valid email addresses")(p.strip())


def validate_json_structure(config, structure):
    def _validate_json_level(config, structure, path):
        missing = set(structure.keys()).difference(set(config.keys()))
        if missing:
            raise ValidationError("Keys {0} are missing".format(", ".join(["->".join(path + [m]) for m in missing])))
        extra = set(config.keys()).difference(set(structure.keys()))
        if extra:
            raise ValidationError("Keys {0} are not allowed".format(", ".join(["->".join(path + [m]) for m in extra])))

        # Keys are correct, validate datatypes
        for k, v in list(config.items()):
            fullkey = "->".join(path + [k])
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
                _validate_json_level(v, structure[k], path + [k])

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
        except Exception as e:
            raise ValidationError("Could not download promotion picture")

        if r.status_code != 200:
            raise ValidationError("Downloading promo picture returned status %s" % r.status_code)
        try:
            img = Image.open(BytesIO(r.content))
            w, h = img.size
            if self.aspect:
                newaspect = round(float(w) / float(h), 2)
                if newaspect != self.aspect:
                    raise ValidationError("Image has aspect ratio %s, must have %s" % (newaspect, self.aspect))

        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError("Failed to parse image: %s" % e)

    def __eq__(self, other):
        return self.aspect == other.aspect


@deconstructible
class ImageValidator(object):
    def __init__(self, formats=['JPEG', ], maxsize=None):
        self.formats = formats
        self.maxsize = maxsize

    def __call__(self, value):
        if value.size is None:
            # This happens when no new file is uploaded, so assume things are fine
            return

        try:
            p = ImageFile.Parser()
            p.feed(value.read())
            p.close()
            img = p.image
        except Exception as e:
            raise ValidationError("Could not parse image: %s" % e)

        if img.format.upper() not in self.formats:
            raise ValidationError("Files of format {0} are not accepted, only {1}".format(img.format, ", ".join(self.formats)))
        if self.maxsize:
            if img.size[0] > self.maxsize[0] or img.size[1] > self.maxsize[1]:
                raise ValidationError("Maximum image size is {}x{}".format(*self.maxsize))
