#
# Return specific settings (not all of them) into the request context,
# so they can be used by all views.
#

from django.conf import settings

def settings_context(request):
	return {
		'currency_abbrev': settings.CURRENCY_ABBREV,
		'currency_symbol': settings.CURRENCY_SYMBOL,
	}
