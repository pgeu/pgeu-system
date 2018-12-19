from django import template

register = template.Library()


@register.filter
def join_on_attr(l, attrname, separator=', '):
    return separator.join(unicode(getattr(i, attrname)) for i in l)
