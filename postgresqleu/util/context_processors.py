#
# Return specific settings (not all of them) into the request context,
# so they can be used by all views.
#

from django.conf import settings
from django.utils.functional import SimpleLazyObject

from postgresqleu.membership.models import Member

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
	}

def settings_context_unicode(request=None):
	# Same as settings_context, except convert all strings to unicode assuming
	# utf-8.
	c = settings_context(request)
	for k,v in c.items():
		if isinstance(v, str):
			c[k] = v.decode('utf8')
	return c

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
