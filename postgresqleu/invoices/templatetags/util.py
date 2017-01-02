from django import template

register = template.Library()

@register.filter
def stringreplace(value, pattern):
	(old,new) = pattern.split(',')
	return value.replace(old,new)
