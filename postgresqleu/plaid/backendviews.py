from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.contrib import messages
from django.conf import settings

from postgresqleu.util.auth import authenticate_backend_group
from postgresqleu.invoices.models import InvoicePaymentMethod


def _do_balance_check(request, paymentmethod, impl):
    balances = impl.get_account_balances()
    if len(balances) == 0:
        # 0 accounts can mean we just haven't updated yet, so set up a loop
        return render(request, 'plaid/check_account.html', {
        })
    if len(balances) != 1:
        messages.error(request, 'Returned {} accounts, should be 1, cannot use this connection.'.format(len(balances)))
        impl.disconnect()
        return HttpResponseRedirect("../")
    elif balances[0]['currency'] != settings.CURRENCY_ISO:
        messages.error(request, 'Currency on account {} is {}, expected {}, cannot use this connection.'.format(balances[0]['accountid'], balances[0]['currency'], settings.CURRENCY_ISO))
        impl.disconnect()
        return HttpResponseRedirect("../")
    else:
        messages.info(request, "Account {} connected.".format(balances[0]['accountid']))
        paymentmethod.config['accountid'] = balances[0]['accountid']
        paymentmethod.save(update_fields=['config', ])
        return HttpResponseRedirect('../')


def connect_to_plaid(request, paymentmethodid):
    authenticate_backend_group(request, 'Invoice managers')

    paymentmethod = get_object_or_404(InvoicePaymentMethod, pk=paymentmethodid, classname='postgresqleu.util.payment.plaid.Plaid')

    impl = paymentmethod.get_implementation()

    if request.method == 'GET' and request.GET.get('check_account', '0') == '1':
        # We're in the check account loop
        return _do_balance_check(request, paymentmethod, impl)

    if request.method == 'POST':
        paymentmethod.config['access_token'] = impl.exchange_token(request.POST['public_token'])
        if not paymentmethod.config['access_token']:
            messages.error(request, 'Could not exchange public token for permanent token.')
            return HttpResponseRedirect('../')

        return _do_balance_check(request, paymentmethod, impl)

    token = impl.get_link_token()
    if not token:
        messages.error(request, "Could not create link token")
        return HttpResponseRedirect("../")

    return render(request, 'plaid/connectaccount.html', {
        'token': token,
    })
