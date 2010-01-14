from django import template

register = template.Library()

@register.simple_tag
def render_payment_url(url, title, email, paytype, cost):
	# Synchronize this with the parser in tools/confreg/paypal.py
	combined_title = "%s - %s (%s)" % (title, paytype, email)
	return url.replace('{{itemname}}',combined_title).replace('{{amount}}',cost)

