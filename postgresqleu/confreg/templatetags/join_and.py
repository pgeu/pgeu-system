from django import template

register = template.Library()


@register.filter
def join_and(value):
    if len(value) == 1:
        # Only one entry, so return it
        return value[0]
    if not isinstance(value, list):
        value = list(value)

    return ", ".join([x for x in value[:-1]]) + " and " + value[-1]
