from django import template

register = template.Library()


@register.filter
def join_on_attr(list_to_join, attrname, separator=', '):
    return separator.join(" ".join([str(getattr(item, a)) for a in attrname.split(',')]) for item in list_to_join)
