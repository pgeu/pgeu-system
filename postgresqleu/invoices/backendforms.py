import django.forms

from postgresqleu.util.backendforms import BackendForm
from postgresqleu.invoices.models import VatRate, InvoicePaymentMethod
from postgresqleu.accounting.models import Account

from postgresqleu.util.payment import payment_implementation_choices


class BackendVatRateForm(BackendForm):
    list_fields = ['name', 'shortname', 'vatpercent', ]

    class Meta:
        model = VatRate
        fields = ['name', 'shortname', 'vatpercent', 'vataccount', ]


class BackendInvoicePaymentMethodNewForm(django.forms.Form):
    helplink = 'payment'
    paymentclass = django.forms.ChoiceField(choices=payment_implementation_choices, label="Payment implementation")

    def get_newform_data(self):
        return self.cleaned_data['paymentclass']


class BackendInvoicePaymentMethodForm(BackendForm):
    helplink = 'payment'
    list_fields = ['name', 'internaldescription', 'classname_short', 'active', 'sortkey', ]
    form_before_new = BackendInvoicePaymentMethodNewForm
    verbose_field_names = {
        'classname_short': 'Implementation',
    }
    coltypes = {
        'Sort key': ['nosearch', ],
    }
    defaultsort = [[4, 'asc']]

    config_fields = []
    config_fieldsets = []
    config_readonly = []

    class Meta:
        model = InvoicePaymentMethod
        fields = ['name', 'internaldescription', 'active', 'sortkey', 'classname']

    @property
    def fieldsets(self):
        return [
            {'id': 'common', 'legend': 'Common', 'fields': ['name', 'internaldescription', 'active', 'sortkey', 'classname'], }
        ] + self.config_fieldsets

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
        for k in self.config_readonly:
            self.fields[k].required = False

        if self.newformdata:
            self.instance.classname = self.newformdata
            self.initial['classname'] = self.newformdata
