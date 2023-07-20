from django import template

register = template.Library()


@register.filter(name='dictlookup')
def dictlookup(value, key):
    return value.get(key, None)


@register.filter(name='arrayelement')
def arrayelement(value, key):
    return value[key]


@register.filter
def join_dictkeys(list_to_join, attrname, separator=', '):
    if not list_to_join:
        return ''
    return separator.join(item[attrname] for item in list_to_join)
