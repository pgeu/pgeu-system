from django import template

register = template.Library()


@register.filter
def join_on_attr(l, attrname, separator=', '):
    return separator.join(str(getattr(i, attrname)) for i in l)
