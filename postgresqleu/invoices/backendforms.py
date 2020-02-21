import django.forms

from postgresqleu.util.backendforms import BackendForm
from postgresqleu.util.widgets import TestButtonWidget
from postgresqleu.invoices.models import VatRate, VatValidationCache, InvoicePaymentMethod
from postgresqleu.accounting.models import Account

from postgresqleu.util.payment import payment_implementation_choices


class BackendVatRateForm(BackendForm):
    helplink = 'payment'
    list_fields = ['name', 'shortname', 'vatpercent', ]

    class Meta:
        model = VatRate
        fields = ['name', 'shortname', 'vatpercent', 'vataccount', ]


class BackendVatValidationCacheForm(BackendForm):
    helplink = 'payment'
    list_fields = ['vatnumber', 'checkedat', ]

    class Meta:
        model = VatValidationCache
        fields = ['vatnumber', ]


class BackendInvoicePaymentMethodNewForm(django.forms.Form):
    helplink = 'payment'
    paymentclass = django.forms.ChoiceField(choices=payment_implementation_choices(), label="Payment implementation")

    def get_newform_data(self):
        return self.cleaned_data['paymentclass']


class BackendInvoicePaymentMethodForm(BackendForm):
    testsettings = django.forms.CharField(required=False, label='Test', widget=TestButtonWidget)

    helplink = 'payment'
    list_fields = ['name', 'internaldescription', 'classname_short', 'active', 'sortkey', ]
    form_before_new = BackendInvoicePaymentMethodNewForm
    verbose_field_names = {
        'classname_short': 'Implementation',
    }
    queryset_extra_fields = {
        'classname_short': r"substring(classname, '[^\.]+$')",
    }
    coltypes = {
        'Sort key': ['nosearch', ],
    }
    defaultsort = [['sortkey', 'asc'], ['name', 'asc']]

    config_fields = []
    config_fieldsets = []
    config_readonly = []

    class Meta:
        model = InvoicePaymentMethod
        fields = ['name', 'internaldescription', 'active', 'sortkey', 'classname']

    @property
    def fieldsets(self):
        fs = [
            {'id': 'common', 'legend': 'Common', 'fields': ['name', 'internaldescription', 'active', 'sortkey', 'classname'], }
        ] + self.config_fieldsets
        if hasattr(self, 'validate_data_for'):
            fs += [
                {'id': 'test', 'legend': 'Test', 'fields': ['testsettings', ]},
            ]

        return fs

    @property
    def readonly_fields(self):
        if hasattr(self, 'validate_data_for'):
            return ['classname', 'testsettings', ] + self.config_readonly
        else:
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
        for k in self.config_readonly:
            self.fields[k].required = False

        if self.newformdata:
            self.instance.classname = self.newformdata
            self.initial['classname'] = self.newformdata

        if not hasattr(self, 'validate_data_for'):
            self.remove_field('testsettings')


class BankfilePaymentMethodChoiceForm(django.forms.Form):
    paymentmethod = django.forms.ModelChoiceField(queryset=None, required=True, label="Payment method")

    def __init__(self, *args, **kwargs):
        methods = kwargs.pop('methods')
        super().__init__(*args, **kwargs)
        self.fields['paymentmethod'].queryset = methods
