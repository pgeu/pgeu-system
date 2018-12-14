from django.template.defaultfilters import stringfilter
from django import template

register = template.Library()


@register.filter(name='alertmap')
@stringfilter
def alertmap(value):
        if value == 'error':
                return 'alert-danger'
        elif value == 'warning':
                return 'alert-warning'
        elif value == 'success':
                return 'alert-success'
        else:
                return 'alert-info'
