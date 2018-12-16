from postgresqleu.util.backendviews import backend_list_editor
from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.elections.backendforms import BackendElectionForm


def edit_election(request, rest):
    authenticate_backend_group(request, 'Election administrators')

    return backend_list_editor(request,
                               None,
                               BackendElectionForm,
                               rest,
                               bypass_conference_filter=True,
                               topadmin='Elections',
                               return_url='/admin/',
    )
