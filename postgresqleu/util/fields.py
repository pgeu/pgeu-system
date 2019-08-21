from django.db import models
from django.core.exceptions import ValidationError
from .forms import ImageBinaryFormField


class LowercaseEmailField(models.EmailField):
    def get_prep_value(self, value):
        value = super(models.EmailField, self).get_prep_value(value)
        if value is not None:
            value = value.lower()
        return value


class ImageBinaryField(models.Field):
    empty_values = [None, b'']

    def __init__(self, *args, **kwargs):
        ml = kwargs.pop('max_length', None)
        super(ImageBinaryField, self).__init__(*args, **kwargs)
        self.max_length = ml

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
