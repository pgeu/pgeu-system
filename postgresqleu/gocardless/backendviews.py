from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.shortcuts import get_object_or_404, render
from django.conf import settings

from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.invoices.models import InvoicePaymentMethod


def connect_to_gocardless(request, paymentmethodid):
    authenticate_backend_group(request, 'Invoice managers')

    paymentmethod = get_object_or_404(InvoicePaymentMethod, pk=paymentmethodid, classname='postgresqleu.util.payment.gocardless.Gocardless')

    impl = paymentmethod.get_implementation()

    if request.method == 'GET' and 'ref' in request.GET:
        # Reference is <paymentmethod>-<uuid>, so split it
        if '-' not in request.GET['ref']:
            return HttpResponse("Invalid reference format")
        if request.GET['ref'].split('-', 1)[0] != str(paymentmethodid):
            return HttpResponse("Invalid reference")

        # Return from authorization, so we should be good to go!
        try:
            impl.finalize_bank_setup()
        except Exception as e:
            return HttpResponse("Error setting up bank connection: {}".format(e))
        messages.info(request, "Bank account configured.")
        return HttpResponseRedirect("../")
    elif request.method == 'GET':
        # First visit, so pick country
        return render(request, 'gocardless/bankselect.html', {
            'country': settings.GOCARDLESS_COUNTRY,
            'banks': impl.get_banks_in_country(settings.GOCARDLESS_COUNTRY),
        })
    elif request.method == 'POST':
        if 'bank' not in request.POST:
            return HttpResponseRedirect(".")

        # Else we have a bank, so get going!
        try:
            link = impl.get_bank_connection_link(request.POST['bank'])
        except Exception as e:
            return HttpResponse("Error getting bank connection: {}".format(e))

        return HttpResponseRedirect(link)
