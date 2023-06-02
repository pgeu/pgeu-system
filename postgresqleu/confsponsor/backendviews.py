from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseRedirect, Http404
from django.contrib import messages
from django.db import transaction
from django.conf import settings

from postgresqleu.util.backendviews import backend_list_editor, backend_process_form
from postgresqleu.confreg.util import get_authenticated_conference
from postgresqleu.digisign.backendviews import pdf_field_editor, pdf_field_preview
from postgresqleu.digisign.pdfutil import fill_pdf_fields

from .models import Sponsor, SponsorshipContract
from .backendforms import BackendSponsorForm
from .backendforms import BackendSponsorshipLevelForm
from .backendforms import BackendSponsorshipContractForm
from .backendforms import BackendShipmentAddressForm
from .backendforms import BackendSponsorshipSendTestForm
from .backendforms import BackendCopyContractFieldsForm
from .util import get_pdf_fields_for_conference


def edit_sponsor(request, urlname, sponsorid):
    conference = get_authenticated_conference(request, urlname)
    sponsor = Sponsor.objects.get(conference=conference, pk=sponsorid)

    return backend_process_form(request,
                                urlname,
                                BackendSponsorForm,
                                sponsor.pk,
                                conference=conference,
                                allow_new=False,
                                allow_delete=not sponsor.invoice,
                                deleted_url='../../',
                                breadcrumbs=[
                                    ('/events/sponsor/admin/{0}/'.format(urlname), 'Sponsors'),
                                    ('/events/sponsor/admin/{0}/{1}/'.format(urlname, sponsor.pk), sponsor.name),
                                ])


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


def edit_shipment_addresses(request, urlname, rest):
    return backend_list_editor(request,
                               urlname,
                               BackendShipmentAddressForm,
                               rest,
                               breadcrumbs=[('/events/sponsor/admin/{0}/'.format(urlname), 'Sponsors'), ])


def edit_sponsorship_contract_fields(request, urlname, contractid):
    conference = get_authenticated_conference(request, urlname)
    contract = SponsorshipContract.objects.get(conference=conference, pk=contractid)

    def _save(jsondata):
        contract.fieldjson = jsondata
        contract.save(update_fields=['fieldjson'])

    return pdf_field_editor(
        request,
        conference,
        contract.contractpdf,
        available_fields=get_pdf_fields_for_conference(conference),
        fielddata=contract.fieldjson,
        savecallback=_save,
        breadcrumbs=[
            ('/events/sponsor/admin/{0}/'.format(urlname), 'Sponsors'),
            ('/events/sponsor/admin/{0}/contracts/'.format(urlname), 'Sponsorship contracts'),
            ('/events/sponsor/admin/{0}/contracts/{1}'.format(urlname, contract.id), contract.contractname),
        ],
    )


def edit_sponsorship_digital_contract_fields(request, urlname, contractid):
    conference = get_authenticated_conference(request, urlname)
    if not conference.contractprovider:
        raise Http404("No contract provider for this conference")

    contract = SponsorshipContract.objects.get(conference=conference, pk=contractid)

    def _save(jsondata):
        contract.fieldjson = jsondata
        contract.save(update_fields=['fieldjson'])

    signer = conference.contractprovider.get_implementation()

    r = signer.edit_digital_fields(
        request,
        conference,
        "{}_{}".format(conference.urlname, contract.contractname.lower()),
        contract.contractpdf,
        contract.fieldjson,
        _save,
        breadcrumbs=[
            ('/events/sponsor/admin/{0}/'.format(urlname), 'Sponsors'),
            ('/events/sponsor/admin/{0}/contracts/'.format(urlname), 'Sponsorship contracts'),
            ('/events/sponsor/admin/{0}/contracts/{1}'.format(urlname, contract.id), contract.contractname),
        ],
    )
    if r is None:
        # indicates we're done
        return HttpResponseRedirect("../")
    return r


def preview_sponsorship_contract_fields(request, urlname, contractid):
    conference = get_authenticated_conference(request, urlname)
    contract = SponsorshipContract.objects.get(conference=conference, pk=contractid)

    return pdf_field_preview(
        request,
        conference,
        contract.contractpdf,
        available_fields=get_pdf_fields_for_conference(conference),
        fielddata=contract.fieldjson,
    )


def send_test_sponsorship_contract(request, urlname, contractid):
    conference = get_authenticated_conference(request, urlname)
    contract = SponsorshipContract.objects.get(conference=conference, pk=contractid)

    if request.method == 'POST':
        form = BackendSponsorshipSendTestForm(contract, request.user, data=request.POST)
        if form.is_valid():
            signer = conference.contractprovider.get_implementation()

            # Start by filling out the static fields
            available_fields = get_pdf_fields_for_conference(conference)
            pdf = fill_pdf_fields(contract.contractpdf, available_fields, contract.fieldjson)

            contractid, error = signer.send_contract(
                conference.contractsendername,
                conference.contractsenderemail,
                form.cleaned_data['recipientname'],
                form.cleaned_data['recipientemail'],
                pdf,
                "{}.pdf".format(contract.contractname),
                "{}: TEST SPONSORSHIP".format(conference.conferencename),
                "Hello!\n\nYou have been sent a test sponsorship contract. Please check it out, but remember this is a test only!\n",
                {
                    'type': 'sponsor',
                    'sponsorid': '-1',
                },
                contract.fieldjson,
                2,  # expires_in
                test=True,
            )
            if error:
                form.add_error(None, 'Failed to send test contract: {}'.format(error))
            else:
                messages.info(request, "Test contract successfully sent, with id {}.".format(contractid))
                return HttpResponseRedirect("../")
    else:
        form = BackendSponsorshipSendTestForm(contract, request.user)

    return render(request, 'confreg/admin_backend_form.html', {
        'basetemplate': 'confreg/confadmin_base.html',
        'conference': conference,
        'whatverb': 'Send test contract',
        'savebutton': 'Send test',
        'form': form,
        'helplink': 'sponsors',
        'breadcrumbs': [
            ('/events/sponsor/admin/{0}/'.format(urlname), 'Sponsors'),
            ('/events/sponsor/admin/{0}/contracts/'.format(urlname), 'Sponsorship contracts'),
            ('/events/sponsor/admin/{0}/contracts/{1}'.format(urlname, contract.id), contract.contractname),
        ],
    })


@transaction.atomic
def copy_sponsorship_contract_fields(request, urlname, contractid):
    conference = get_authenticated_conference(request, urlname)
    contract = SponsorshipContract.objects.get(conference=conference, pk=contractid)

    if request.method == 'POST':
        form = BackendCopyContractFieldsForm(contract, data=request.POST)
        if form.is_valid():
            copyfrom = get_object_or_404(SponsorshipContract, conference=conference, pk=form.cleaned_data['copyfrom'])
            contract.fieldjson = copyfrom.fieldjson
            contract.save(update_fields=['fieldjson'])
            messages.info(request, "Fields copied from {} to {}".format(copyfrom.contractname, contract.contractname))
            return HttpResponseRedirect("../")
    else:
        form = BackendCopyContractFieldsForm(contract)

    return render(request, 'confsponsor/copy_contract_fields.html', {
        'conference': conference,
        'whatverb': 'Copy contract fields',
        'savebutton': 'Copy fields',
        'form': form,
        'helplink': 'sponsors',
        'breadcrumbs': [
            ('/events/sponsor/admin/{0}/'.format(urlname), 'Sponsors'),
            ('/events/sponsor/admin/{0}/contracts/'.format(urlname), 'Sponsorship contracts'),
            ('/events/sponsor/admin/{0}/contracts/{1}'.format(urlname, contract.id), contract.contractname),
        ],
    })
