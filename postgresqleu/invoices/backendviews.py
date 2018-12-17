from postgresqleu.util.backendviews import backend_list_editor
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.invoices.backendforms import BackendVatRateForm


def edit_vatrate(request, rest):
    authenticate_backend_group(request, 'Invoice managers')

    return backend_list_editor(request,
                               None,
                               BackendVatRateForm,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='Invoices',
                               return_url='/admin/',
    )
