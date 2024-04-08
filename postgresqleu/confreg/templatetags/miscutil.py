from django import template
from django.utils.safestring import mark_safe

import json

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


@register.filter(name='jsonstruct')
def jsonstruct(value):
    return mark_safe(json.dumps(value))


@register.filter(name='subtract')
def subtract(value, arg):
    return value - arg
