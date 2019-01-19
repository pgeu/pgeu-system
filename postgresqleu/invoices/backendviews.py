from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from postgresqleu.util.backendviews import backend_list_editor
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.util.payment import payment_implementations

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.invoices.backendforms import BackendVatRateForm
from postgresqleu.invoices.backendforms import BackendInvoicePaymentMethodForm


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


def _load_formclass(classname):
    pieces = classname.split('.')
    modname = '.'.join(pieces[:-1])
    classname = pieces[-1]
    mod = __import__(modname, fromlist=[classname, ])
    if hasattr(getattr(mod, classname), 'backend_form_class'):
        return getattr(mod, classname).backend_form_class
    else:
        return BackendInvoicePaymentMethodForm


def edit_paymentmethod(request, rest):
    if not request.user.is_superuser:
        raise PermissionDenied("Access denied")

    u = rest and rest.rstrip('/') or rest

    formclass = BackendInvoicePaymentMethodForm
    if u and u != '' and u.isdigit():
        # Editing an existing one, so pick the correct subclass!
        pm = get_object_or_404(InvoicePaymentMethod, pk=u)
        formclass = _load_formclass(pm.classname)
    elif u == 'new':
        if '_newformdata' in request.POST or 'paymentclass' in request.POST:
            if '_newformdata' in request.POST:
                c = request.POST['_newformdata']
            else:
                c = request.POST['paymentclass']

            if c not in payment_implementations:
                raise PermissionDenied()

            formclass = _load_formclass(c)

    return backend_list_editor(request,
                               None,
                               formclass,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='Invoices',
                               return_url='/admin/',
    )
