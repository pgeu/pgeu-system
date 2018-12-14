from django import template
from django.utils.safestring import mark_safe
import re

register = template.Library()

re_leadingspace = re.compile('^ +')

@register.filter
def leadingnbsp(value):
    if value.startswith(' '):
        return mark_safe(re_leadingspace.sub(lambda m: m.group(0).replace(' ', '&nbsp;'), value))
    else:
        return value
