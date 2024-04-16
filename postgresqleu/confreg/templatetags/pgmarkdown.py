# Filter wrapping the python markdown library into a django template filter
from django import template
from django.utils.encoding import force_str
from django.utils.safestring import mark_safe

from postgresqleu.util.markup import pgmarkdown

register = template.Library()


@register.filter(is_safe=True)
def markdown(value, args=''):
    return mark_safe(pgmarkdown(
        force_str(value),
    ))
