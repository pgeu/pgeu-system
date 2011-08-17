from django import template

register = template.Library()

PAYPAL_BASEURL="https://www.paypal.com/cgi-bin/webscr?cmd"
PAYPAL_COMMON="&business=paypal%40postgresql%2eeu&lc=GB&currency_code=EUR&button_subtype=services&no_note=1&no_shipping=1&bn=PP%2dBuyNowBF%3abtn_buynowCC_LG%2egif%3aNonHosted&charset=utf-8"

@register.simple_tag
def render_paypal_url(paypalrecip, title, email, paytype, cost, additionaloptions):
	# Synchronize this with the parser in tools/confreg/paypal.py
	itemstr = "%s - %s (%s)" % (title, paytype, email)

	options = additionaloptions.all()

	if len(options) == 0:
		# Just a simple order, with no additional options - don't create a cart
		return "%s=_xclick&item_name=%s&amount=%s%%2e00%s" % (
			PAYPAL_BASEURL,
			itemstr,
			cost,
			PAYPAL_COMMON,
			)

	# Has multiple items, so we need to create a cart
	cartstr = "item_name_1=%s&amount_1=%s%%2e00" % (itemstr, cost)
	for i in range(0, len(options)):
		cartstr += "&item_name_%s=%s&amount_%s=%s%%2e00" % (
			i+2,
			options[i].name,
			i+2,
			options[i].cost,
			)

	return "%s=_cart&upload=1&%s%s" % (
		PAYPAL_BASEURL,
		cartstr,
		PAYPAL_COMMON)
