from django.http import Http404, HttpResponse
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from postgresqleu.util.crypto import rsa_verify_string_sha1
from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.scheduler.util import trigger_immediate_job_run

import base64
from datetime import timedelta


# From the TW documentation
_transferwise_public_key_str = base64.b64decode("""MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvO8vXV+JksBzZAY6GhSO
XdoTCfhXaaiZ+qAbtaDBiu2AGkGVpmEygFmWP4Li9m5+Ni85BhVvZOodM9epgW3F
bA5Q1SexvAF1PPjX4JpMstak/QhAgl1qMSqEevL8cmUeTgcMuVWCJmlge9h7B1CS
D4rtlimGZozG39rUBDg6Qt2K+P4wBfLblL0k4C4YUdLnpGYEDIth+i8XsRpFlogx
CAFyH9+knYsDbR43UJ9shtc42Ybd40Afihj8KnYKXzchyQ42aC8aZ/h5hyZ28yVy
Oj3Vos0VdBIs/gAyJ/4yyQFCXYte64I7ssrlbGRaco4nKF3HmaNhxwyKyJafz19e
HwIDAQAB
""")


@csrf_exempt
def webhook(request, methodid, hooktype):
    if request.method != 'POST':
        raise Http404()
    if hooktype not in ('balance', ):
        raise Http404()

    # Mandatory headers
    if 'X-Signature' not in request.headers or 'X-Delivery-Id' not in request.headers:
        raise Http404()

    # Verify the signature
    if not rsa_verify_string_sha1(
            _transferwise_public_key_str,
            request.body,
            base64.b64decode(request.headers['X-Signature']),
    ):
        raise PermissionDenied("Invalid webhook signature")

    # Verify that it's for a valid payment method
    get_object_or_404(InvoicePaymentMethod, pk=methodid, active=True)

    # Valid signature and requests looks OK, now we can process the actual hook.
    if hooktype == 'balance':
        # Balance updated -- we just schedule the poll job, since we don't have all the details
        # in the hook.
        trigger_immediate_job_run('transferwise_fetch_transactions', timedelta(seconds=30))
        print("SCHEDULING HOOK!")
    else:
        raise Exception("Cannot happen")

    return HttpResponse("OK")
