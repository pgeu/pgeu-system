from django import template

from postgresqleu.util.currency import format_currency as format_currency_func

register = template.Library()


@register.filter
def format_currency(value):
    return format_currency_func(value)
