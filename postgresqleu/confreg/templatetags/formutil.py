from django import template

register = template.Library()

@register.filter(is_safe=True)
def label_class(value, arg):
	return value.label_tag(attrs={'class': arg})

@register.filter(is_safe=True)
def field_class(value, arg):
	prevclass = value.field.widget.attrs.get('class', '')
	if prevclass:
		newclass = "{0} {1}".format(arg, prevclass)
	else:
		newclass = arg
	return value.as_widget(attrs={"class": newclass})

@register.filter(is_safe=True)
def ischeckbox(obj):
	return obj.field.widget.__class__.__name__ == "CheckboxInput" and not getattr(obj.field, 'regular_field', False)

@register.filter(is_safe=True)
def isrequired_error(obj):
	if obj.errors and obj.errors[0] == u"This field is required.":
		return True
	return False
