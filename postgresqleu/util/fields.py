from django.db import models
from django.core.exceptions import ValidationError
from .forms import ImageBinaryFormField, PdfBinaryFormField

from PIL import ImageFile

from postgresqleu.util.magic import magicdb


class LowercaseEmailField(models.EmailField):
    def get_prep_value(self, value):
        value = super(models.EmailField, self).get_prep_value(value)
        if value is not None:
            value = value.lower()
        return value


class ImageBinaryField(models.Field):
    empty_values = [None, b'']

    def __init__(self, max_length, *args, **kwargs):
        self.max_resolution = kwargs.pop('max_resolution', None)
        super(ImageBinaryField, self).__init__(*args, **kwargs)
        self.max_length = max_length

    def deconstruct(self):
        name, path, args, kwargs = super(ImageBinaryField, self).deconstruct()
        return name, path, args, kwargs

    def get_internal_type(self):
        return "ImageBinaryField"

    def get_placeholder(self, value, compiler, connection):
        return '%s'

    def get_default(self):
        return b''

    def db_type(self, connection):
        return 'bytea'

    def get_db_prep_value(self, value, connection, prepared=False):
        value = super(ImageBinaryField, self).get_db_prep_value(value, connection, prepared)
        if value is not None:
            return connection.Database.Binary(value)
        return value

    def value_to_string(self, obj):
        """Binary data is serialized as base64"""
        return b64encode(force_bytes(self.value_from_object(obj))).decode('ascii')

    def to_python(self, value):
        if self.max_length is not None and len(value) > self.max_length:
            raise ValidationError("Maximum size of file is {} bytes".format(self.max_length))

        if isinstance(value, memoryview):
            v = bytes(value)
        else:
            v = value
        try:
            p = ImageFile.Parser()
            p.feed(v)
            p.close()
            img = p.image
        except Exception as e:
            raise ValidationError("Could not parse image: %s" % e)

        if img.format.upper() != 'JPEG':
            raise ValidationError("Only JPEG files are allowed")

        if self.max_resolution:
            if img.size[0] > self.max_resolution[0] or img.size[1] > self.max_resolution[1]:
                raise ValidationError("Maximum image size is {}x{}".format(*self.max_resolution))

        return value

    def save_form_data(self, instance, data):
        if data is not None:
            if not data:
                data = b''
            setattr(instance, self.name, data)

    def formfield(self, **kwargs):
        defaults = {'form_class': ImageBinaryFormField}
        defaults.update(kwargs)
        return super(ImageBinaryField, self).formfield(**defaults)


class PdfBinaryField(ImageBinaryField):
    def get_internal_type(self):
        return "PdfBinaryField"

    def formfield(self, **kwargs):
        defaults = {'form_class': PdfBinaryFormField}
        defaults.update(kwargs)
        return super(PdfBinaryField, self).formfield(**defaults)

    def to_python(self, value):
        if self.max_length is not None and len(value) > self.max_length:
            raise ValidationError("Maximum size of file is {} bytes".format(self.max_length))

        mtype = magicdb.buffer(value)
        if not mtype.startswith('application/pdf'):
            raise ValidationError("File must be PDF, not %s" % mtype)

        return value
