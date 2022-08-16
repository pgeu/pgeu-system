from django.utils import timezone

from datetime import timedelta
import requests

from postgresqleu.invoices.models import VatValidationCache


def validate_eu_vat_number(number):
    if VatValidationCache.objects.filter(vatnumber=number, checkedat__gt=timezone.now() - timedelta(days=90)).exists():
        return None

    country = number[:2]
    numberonly = number[2:]

    try:
        r = requests.get('https://ec.europa.eu/taxation_customs/vies/rest-api/ms/{}/vat/{}'.format(country, numberonly), timeout=15)
        r.raise_for_status()
        j = r.json()
        if j.get('isValid', False):
            VatValidationCache(vatnumber=number).save()
            return None
        return "Invalid VAT number according to validation service: {}".format(j.get('userError', ''))
    except Exception as e:
        return "Unable to reach validation service"
