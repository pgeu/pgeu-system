#
# Return specific settings (not all of them) into the request context,
# so they can be used by all views.
#

from django.conf import settings
from django.utils.functional import SimpleLazyObject


def settings_context(request=None):
    return {
        'org_name': settings.ORG_NAME,
        'org_short_name': settings.ORG_SHORTNAME,
        'treasurer_email': settings.TREASURER_EMAIL,
        'sitebase': settings.SITEBASE,
        'currency_abbrev': settings.CURRENCY_ABBREV,
        'currency_symbol': settings.CURRENCY_SYMBOL,
        'is_debugging': settings.DEBUG,
        'eu_vat': settings.EU_VAT,
        'modules': {
            'news': settings.ENABLE_NEWS,
            'membership': settings.ENABLE_MEMBERSHIP,
            'elections': settings.ENABLE_ELECTIONS,
        }
    }


if settings.ENABLE_MEMBERSHIP:
    from postgresqleu.membership.models import Member


def member_context(request=None):
    def _member():
        if not request.user.is_authenticated():
            return None

        try:
            return Member.objects.get(user=request.user)
        except Member.DoesNotExist:
            return None

    return {
        'member': SimpleLazyObject(_member),
    }
