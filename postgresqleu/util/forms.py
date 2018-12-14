from django import forms
from django.forms import ValidationError
from django.core.signing import Signer, BadSignature
from django.contrib.postgres.fields import ArrayField

import cPickle
import base64
from itertools import groupby

class _ValidatorField(forms.Field):
    required = True
    widget = forms.HiddenInput

class ConcurrentProtectedModelForm(forms.ModelForm):
    _validator = _ValidatorField()

    def _filter_initial(self):
        # self.initial will include things given in the URL after ?, so filter it to
        # only include items that are actually form fields.
        return {k:v for k,v in self.initial.items() if k in self.fields.keys()}

    def update_protected_fields(self):
        self.fields['_validator'].initial = Signer().sign(base64.urlsafe_b64encode(cPickle.dumps(self._filter_initial(), -1)))
    def __init__(self, *args, **kwargs):
        r = super(ConcurrentProtectedModelForm, self).__init__(*args, **kwargs)
        self.update_protected_fields()
        return r

    def clean(self):
        # Process the form itself
        data = super(ConcurrentProtectedModelForm, self).clean()

        if not self.instance.pk:
            # No primary key, means instance was not previously saved, so there can be
            # no concurrent edit.
            return data

        # Fetch the list of values from the currernt object in the db
        i = self._filter_initial()
        try:
            s = Signer().unsign(self.cleaned_data['_validator'])
            b = base64.urlsafe_b64decode(s.encode('utf8'))
            d = cPickle.loads(b)
            for k,v in d.items():
                if i[k] != v:
                    raise ValidationError("Concurrent modification of field {0}. Please reload the form and try again.".format(k))
        except BadSignature:
            raise ValidationError("Form has been tampered with!")
        except TypeError:
            raise ValidationError("Bad serialized form state")
        except cPickle.UnpicklingError:
            raise ValidationError("Bad serialized python form state")

        return data


class ChoiceArrayField(ArrayField):
    def formfield(self, **kwargs):
        defaults = {
            'form_class': forms.MultipleChoiceField,
            'choices': self.base_field.choices,
        }
        defaults.update(kwargs)
        return super(ArrayField, self).formfield(**defaults)


class GroupedIterator(forms.models.ModelChoiceIterator):
    def __iter__(self):
        for group, choices in groupby(self.queryset.all().order_by(self.field.groupfield, *self.field.orderby),
                                      key=lambda x: getattr(x, self.field.groupfield)):
            yield (group,
                   [self.choice(c) for c in choices])

class Grouped(object):
    def __init__(self, groupfield, queryset, *args, **kwargs):
        self.orderby = queryset.query.order_by
        super(Grouped, self).__init__(*args, queryset=queryset, **kwargs)
        self.groupfield = groupfield

    def _get_choices(self):
        return GroupedIterator(self)

class GroupedModelMultipleChoiceField(Grouped, forms.ModelMultipleChoiceField):
    choices = property(Grouped._get_choices, forms.ModelMultipleChoiceField._set_choices)
