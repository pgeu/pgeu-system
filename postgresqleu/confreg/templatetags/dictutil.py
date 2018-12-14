from django import template

register = template.Library()


@register.filter(name='dictlookup')
def dictlookup(value, key):
    return value.get(key, None)
