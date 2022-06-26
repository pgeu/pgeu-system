from django.db import models
from django.core.exceptions import ValidationError
from .forms import ImageBinaryFormField, PdfBinaryFormField

import io

from PIL import Image, ImageFile

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
        self.resolution = kwargs.pop('resolution', None)
        self.auto_scale = kwargs.pop('auto_scale', False)
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

        if img.format.upper() not in ('JPEG', 'PNG'):
            raise ValidationError("Only JPEG or PNG files are allowed")

        if self.resolution:
            if img.size[0] != self.resolution[0] or img.size[1] != self.resolution[1]:
                if self.auto_scale:
                    scale = min(
                        float(self.resolution[0]) / float(img.size[0]),
                        float(self.resolution[1]) / float(img.size[1]),
                    )
                    newimg = img.resize(
                        (int(img.size[0] * scale), int(img.size[1] * scale)),
                        Image.BICUBIC,
                    )
                    saver = io.BytesIO()
                    if newimg.size[0] != newimg.size[1]:
                        # This is not a square, so we have to roll it again
                        centeredimg = Image.new('RGBA', self.resolution)
                        centeredimg.paste(newimg, (
                            (self.resolution[0] - newimg.size[0]) // 2,
                            (self.resolution[1] - newimg.size[1]) // 2,
                        ))
                        centeredimg.save(saver, format='PNG')
                    else:
                        newimg.save(saver, format="PNG")
                    value = saver.getvalue()
                else:
                    raise ValidationError("Image size must be {}x{}".format(*self.resolution))

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
