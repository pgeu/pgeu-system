from django.shortcuts import render

from postgresqleu.util.backendviews import backend_list_editor
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.util.db import exec_to_dict

from postgresqleu.accounting.backendforms import BackendAccountClassForm
from postgresqleu.accounting.backendforms import BackendAccountGroupForm
from postgresqleu.accounting.backendforms import BackendAccountForm
from postgresqleu.accounting.backendforms import BackendObjectForm


def edit_accountclass(request, rest):
    authenticate_backend_group(request, 'Accounting managers')

    return backend_list_editor(request,
                               None,
                               BackendAccountClassForm,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='Accounting',
                               return_url='/admin/',
    )


def edit_accountgroup(request, rest):
    authenticate_backend_group(request, 'Accounting managers')

    return backend_list_editor(request,
                               None,
                               BackendAccountGroupForm,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='Accounting',
                               return_url='/admin/',
    )


def edit_account(request, rest):
    authenticate_backend_group(request, 'Accounting managers')

    return backend_list_editor(request,
                               None,
                               BackendAccountForm,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='Accounting',
                               return_url='/admin/',
    )


def edit_object(request, rest):
    authenticate_backend_group(request, 'Accounting managers')

    return backend_list_editor(request,
                               None,
                               BackendObjectForm,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='Accounting',
                               return_url='/admin/',
    )


def accountstructure(request):
    authenticate_backend_group(request, 'Accounting managers')

    accounts = exec_to_dict("""SELECT ac.id AS classid, ac.name AS classname, ac.inbalance,
ag.id AS groupid, ag.name AS groupname,
a.id AS accountid, a.num AS accountnum, a.name AS accountname
FROM accounting_accountclass ac
INNER JOIN accounting_accountgroup ag ON ag.accountclass_id=ac.id
INNER JOIN accounting_account a ON a.group_id=ag.id
ORDER BY a.num""")

    return render(request, 'accounting/structure.html', {
        'accounts': accounts,
        'topadmin': 'Accounting',
        'helplink': 'accounting',
    })
