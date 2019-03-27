from django import template

register = template.Library()


@register.filter
def join_on_attr(l, attrname, separator=', '):
    return separator.join(" ".join([str(getattr(i, a)) for a in attrname.split(',')]) for i in l)
