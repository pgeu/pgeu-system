import django.forms
import django.forms.widgets
from django.core.validators import MinValueValidator, MaxValueValidator

from postgresqleu.util.forms import ConcurrentProtectedModelForm
from postgresqleu.util.widgets import HtmlDateInput

import datetime
from functools import reduce


class _NewFormDataField(django.forms.Field):
    required = True
    widget = django.forms.HiddenInput


class BackendForm(ConcurrentProtectedModelForm):
    list_fields = None
    list_order_by = None
    selectize_multiple_fields = None
    json_fields = None
    json_form_fields = None
    markdown_fields = []
    dynamic_preview_fields = []
    vat_fields = {}
    verbose_field_names = {}
    exclude_date_validators = []
    form_before_new = None
    newformdata = None
    _newformdata = _NewFormDataField()
    allow_copy_previous = False
    copy_transform_form = None
    coltypes = {}
    filtercolumns = {}
    defaultsort = []
    readonly_fields = []
    file_fields = []
    linked_objects = {}
    auto_cascade_delete_to = []
    fieldsets = []
    allow_email = False
    force_insert = False
    helplink = None

    def __init__(self, conference, *args, **kwargs):
        self.conference = conference

        if 'newformdata' in kwargs:
            self.newformdata = kwargs['newformdata']
            del kwargs['newformdata']

        super(BackendForm, self).__init__(*args, **kwargs)

        if self.newformdata:
            self.fields['_newformdata'].initial = self.newformdata
        else:
            del self.fields['_newformdata']

        if self.json_form_fields:
            for fn, ffields in self.json_form_fields.items():
                if getattr(self.instance, fn):
                    for fld in ffields:
                        self.initial[fld] = getattr(self.instance, fn).get(fld, None)
            self.update_protected_fields()

        self.fix_fields()
        self.fix_selectize_fields(**kwargs)

        # Runtime validate fieldsets. It's ugly as fsck to do this at runtime,
        # but meh, this isn't used that often so...
        if self.fieldsets:
            all_fields = set([f for f in self.fields if f not in ('_validator', '_newformdata')])
            all_fieldsetted_fields = set(reduce(lambda x, y: x + y, [v['fields'] for v in self.fieldsets]))
            missing = all_fields.difference(all_fieldsetted_fields)
            if missing:
                raise Exception("ERROR: fields %s are not in a fieldset (fieldsets have %s)" % (", ".join(missing), ", ".join(all_fieldsetted_fields)))

        for k, v in list(self.fields.items()):
            # Adjust widgets
            if isinstance(v, django.forms.fields.DateField):
                v.widget = HtmlDateInput()

            # Any datetime or date fields that are not explicitly excluded will be forced to be within
            # the conference dates.
            if self.conference:
                if isinstance(v, django.forms.fields.DateTimeField) and k not in self.exclude_date_validators:
                    v.validators.extend([
                        MinValueValidator(datetime.datetime.combine(self.conference.startdate, datetime.time(0, 0, 0))),
                        MaxValueValidator(datetime.datetime.combine(self.conference.enddate + datetime.timedelta(days=1), datetime.time(0, 0, 0))),
                    ])
                elif isinstance(v, django.forms.fields.DateField) and k not in self.exclude_date_validators:
                    v.validators.extend([
                        MinValueValidator(self.conference.startdate),
                        MaxValueValidator(self.conference.enddate),
                    ])

        for field, vattype in list(self.vat_fields.items()):
            self.fields[field].widget.attrs['class'] = 'backend-vat-field backend-vat-{0}-field'.format(vattype)

        for field in self.readonly_fields:
            self.fields[field].widget.attrs['readonly'] = 'true'

    def fix_selectize_fields(self, **kwargs):
        if not self.selectize_multiple_fields:
            return

        for field, lookup in list(self.selectize_multiple_fields.items()):
            # If this is a postback of a selectize field, it may contain ids that are not currently
            # stored in the field. They must still be among the *allowed* values of course, which
            # are handled by the existing queryset on the field.
            if self.instance.pk:
                # If this object isn't created yet, then it by definition has no related
                # objects, so just bypass the collection of values since it will cause
                # errors.
                vals = [o.pk for o in getattr(self.instance, field).all()]
            else:
                vals = []
            if 'data' in kwargs and str(field) in kwargs['data']:
                vals.extend([x for x in kwargs['data'].getlist(field)])
            self.fields[field].widget.attrs['data-selecturl'] = lookup.url
            self.fields[field].queryset = self.fields[field].queryset.filter(pk__in=set(vals))
            self.fields[field].label_from_instance = lookup.label_from_instance

    def remove_field(self, fieldname):
        # Remove base field
        del self.fields[fieldname]
        # And then remove any references in a fieldset
        for fs in self.fieldsets:
            if fieldname in fs['fields']:
                fs['fields'].remove(fieldname)

    def fix_fields(self):
        pass

    @classmethod
    def get_column_filters(cls, conference):
        return {}

    @classmethod
    def get_assignable_columns(cls, conference):
        return {}

    def pre_create_item(self):
        pass

    @property
    def get_json_merge_data(self):
        pass

    @classmethod
    def get_initial(self):
        return {}

    @classmethod
    def get_field_verbose_name(self, f):
        if f in self.verbose_field_names:
            return self.verbose_field_names[f]
        return self.Meta.model._meta.get_field(f).verbose_name.capitalize()

    @classmethod
    def numeric_defaultsort(cls):
        return [[cls.list_fields.index(fn), d] for fn, d in cls.defaultsort]

    @property
    def validator_field(self):
        return self['_validator']

    @property
    def newformdata_field(self):
        if '_newformdata' in self.fields:
            return self['_newformdata']

    def get(self, name, default=None):
        # Implement the get operator, for template functions to get a field
        return self[name]
