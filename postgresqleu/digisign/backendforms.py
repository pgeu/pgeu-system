from django import forms

from postgresqleu.util.backendforms import BackendForm, BackendBeforeNewForm
from postgresqleu.util.forms import SelectSetValueField

from postgresqleu.digisign.models import DigisignProvider
from postgresqleu.digisign.util import digisign_provider_choices


class BackendDigisignProviderNewForm(BackendBeforeNewForm):
    helplink = 'digisign'
    classname = forms.ChoiceField(choices=digisign_provider_choices(), label='Implementation class')

    def get_newform_data(self):
        return self.cleaned_data['classname']


class BackendProviderForm(BackendForm):
    list_fields = ['name', 'displayname', 'active', 'classname_short']
    helplink = 'digisign'
    form_before_new = BackendDigisignProviderNewForm
    verbose_field_names = {
        'classname_short': 'Implementation',
    }
    queryset_extra_fields = {
        'classname_short': r"substring(classname, '[^\.]+$')",
    }
    extrabuttons = [
        ('View log', 'log/'),
    ]

    config_fields = []
    config_fieldsets = []
    config_readonly = []

    class Meta:
        model = DigisignProvider
        fields = ['name', 'displayname', 'active', 'classname']

    @property
    def fieldsets(self):
        fs = [
            {'id': 'common', 'legend': 'Common', 'fields': ['name', 'displayname', 'active', 'classname'], }
        ] + self.config_fieldsets

        return fs

    @property
    def readonly_fields(self):
        return ['classname', ] + self.config_readonly

    @property
    def exclude_fields_from_validation(self):
        return self.config_readonly

    @property
    def json_form_fields(self):
        return {
            'config': self.config_fields,
        }

    def fix_fields(self):
        if self.newformdata:
            self.instance.classname = self.newformdata
            self.initial['classname'] = self.newformdata
