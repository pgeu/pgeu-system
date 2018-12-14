from django.template.defaultfilters import stringfilter
from django import template

register = template.Library()


@register.filter(name='docslink')
@stringfilter
def docslink(value):
    if '#' in value:
        return '{0}/#{1}'.format(*value.split('#'))
    return value + '/'
