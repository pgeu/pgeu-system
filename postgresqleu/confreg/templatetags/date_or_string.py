from django import template

from datetime import date

register = template.Library()

@register.filter
def date_or_string(value):
	if value is None:
		return ""

	if isinstance(value, date):
		return value.strftime("%Y-%m-%d")

	return value
