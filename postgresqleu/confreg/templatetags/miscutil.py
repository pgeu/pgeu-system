from django import template

register = template.Library()


@register.filter(name='isboolean')
def isboolean(value):
    return isinstance(value, bool)


@register.filter(name='vartypename')
def vartypename(value):
    return type(value).__name__


@register.filter(name='striplinebreaks')
def stripnewline(value):
    return value.replace("\n", " ")
