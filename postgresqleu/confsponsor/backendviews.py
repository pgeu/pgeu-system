from postgresqleu.confreg.backendviews import backend_list_editor

from backendforms import BackendSponsorshipLevelForm
from backendforms import BackendSponsorshipContractForm

def edit_sponsorship_levels(request, urlname, rest):
	return backend_list_editor(request,
							   urlname,
							   BackendSponsorshipLevelForm,
							   rest,
							   breadcrumbs=[('/events/sponsor/admin/{0}/'.format(urlname), 'Sponsors'), ])

def edit_sponsorship_contracts(request, urlname, rest):
	return backend_list_editor(request,
							   urlname,
							   BackendSponsorshipContractForm,
							   rest,
							   breadcrumbs=[('/events/sponsor/admin/{0}/'.format(urlname), 'Sponsors'), ])
