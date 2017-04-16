#
# Return specific settings (not all of them) into the request context,
# so they can be used by all views.
#

from django.conf import settings

def settings_context(request):
	return {
		'org_name': settings.ORG_NAME,
		'treasurer_email': settings.TREASURER_EMAIL,
		'sitebase': settings.SITEBASE,
		'currency_abbrev': settings.CURRENCY_ABBREV,
		'currency_symbol': settings.CURRENCY_SYMBOL,
		'is_debugging': settings.DEBUG,
	}
