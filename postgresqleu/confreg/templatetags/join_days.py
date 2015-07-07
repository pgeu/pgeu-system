from django import template

register = template.Library()

@register.filter
def join_days(value):
	# Value is a list of RegistrationDay:s
	if len(value) == 1:
		# Only one entry, so return it
		return value[0].shortday()
	value = list(value)
	# Else we have more than one
	return ", ".join([x.shortday() for x in value[:-1]]) + " and " + value[-1].shortday()
