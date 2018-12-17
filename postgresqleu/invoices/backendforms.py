from postgresqleu.util.backendforms import BackendForm
from postgresqleu.invoices.models import VatRate


class BackendVatRateForm(BackendForm):
    list_fields = ['name', 'shortname', 'vatpercent', ]

    class Meta:
        model = VatRate
        fields = ['name', 'shortname', 'vatpercent', 'vataccount', ]
