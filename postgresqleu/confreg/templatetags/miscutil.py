from django import template

register = template.Library()


@register.filter(name='isboolean')
def isboolean(value):
    return isinstance(value, bool)
