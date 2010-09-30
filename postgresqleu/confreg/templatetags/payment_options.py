from django import template

register = template.Library()

@register.simple_tag
def render_payment_url(url, title, email, paytype, cost, additionaloptions):
	# Synchronize this with the parser in tools/confreg/paypal.py
	options = additionaloptions.all()

	allpaytypes = [paytype]
	allpaytypes.extend([option.name for option in options])

	fullcost = int(cost)
	for option in options:
		fullcost += option.cost

	combined_title = "%s - %s (%s)" % (title, ", ".join(allpaytypes), email)
	return url.replace('{{itemname}}',combined_title).replace('{{amount}}',unicode(fullcost))

