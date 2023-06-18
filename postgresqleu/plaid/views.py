from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicNumbers
import hashlib
import hmac
import json
import jwt
import time

from postgresqleu.invoices.models import InvoicePaymentMethod
from postgresqleu.scheduler.util import trigger_immediate_job_run
from postgresqleu.plaid.models import PlaidWebhookData


def _validate_signature(request, method):
    signed_jwt = request.META.get('HTTP_PLAID_VERIFICATION', '')
    current_key_id = jwt.get_unverified_header(signed_jwt)['kid']

    impl = method.get_implementation()
    key = impl.get_signing_key(current_key_id)
    if not key:
        print("Signing key {} not found".format(current_key_id))
        return False

    if key.get('expired_at', None) is not None:
        print("Key expired")
        return False

    if key['kty'] != 'EC' or key['alg'] != 'ES256' or key['crv'] != 'P-256':
        print("Unknown type of key")
        return False

    # This is included in newest versions of pyjwt, but not the ones currently deployed,
    # so steal their implementation over here.
    x = jwt.utils.base64url_decode(key.get("x"))
    y = jwt.utils.base64url_decode(key.get("y"))

    try:
        curve_obj = SECP256R1()
        public_numbers = EllipticCurvePublicNumbers(
            x=int.from_bytes(x, byteorder="big"),
            y=int.from_bytes(y, byteorder="big"),
            curve=curve_obj,
        )

        claims = jwt.decode(signed_jwt, public_numbers.public_key(), algorithms=['ES256'])
    except jwt.exceptions.PyJWTError as e:
        print("Exception validating jwt: {}".format(e))
        return False
    except Exception as ee:
        print("Exception processing jwt: {}".format(ee))
        return False

    if claims["iat"] < time.time() - 5 * 60:
        print("Claim expired")
        return False

    m = hashlib.sha256()
    m.update(request.body)
    body_hash = m.hexdigest()

    if not hmac.compare_digest(body_hash, claims['request_body_sha256']):
        print("Hash of webhook did not validate")
        return False
    return True


@csrf_exempt
def webhook(request, methodid):
    if request.method != 'POST':
        raise Http404()

    if 'application/json' not in request.META['CONTENT_TYPE']:
        print(request.META['CONTENT_TYPE'])
        return HttpResponse("Invalid content type", status=400)

    try:
        j = json.loads(request.body)
    except json.decoder.JSONDecodeError:
        return HttpResponse("Invalid json", status=400)

    # Store a copy of the webhook, for tracing
    PlaidWebhookData(
        source=request.META['REMOTE_ADDR'],
        signature=request.META.get('HTTP_PLAID_VERIFICATION', ''),
        hook_code=j.get('webhook_code', None),
        contents=j,
    ).save()

    # Process any type of webhook we know what to do with

    if j.get('webhook_type', None) == 'TRANSACTIONS' and j.get('webhook_code', None) == 'SYNC_UPDATES_AVAILABLE':
        # Just ensure the object exists, and then throw it away, since we
        # don't have a way to pass parameters to the job. We assume the
        # number of plaid accounts to poll is never *that* big, and it's not
        # like we expects several of these hooks to arrive per minute or so..
        method = get_object_or_404(InvoicePaymentMethod, pk=methodid, classname="postgresqleu.util.payment.plaid.Plaid")
        if not _validate_signature(request, method):
            return HttpResponse("Invalid signature", status=400)

        trigger_immediate_job_run('plaid_fetch_transactions')

    return HttpResponse("OK", content_type="text/plain")
