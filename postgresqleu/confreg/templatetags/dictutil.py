from django import template

register = template.Library()


@register.filter(name='dictlookup')
def dictlookup(value, key):
    return value.get(key, None)


@register.filter(name='arrayelement')
def arrayelement(value, key):
    return value[key]


# Use comma to select a different separator
@register.filter
def join_dictkeys(list_to_join, attrname):
    if not list_to_join:
        return ''
    if ',' in attrname:
        attrname, separator = attrname.split(',', 1)
    else:
        separator = ', '
    return separator.join(str(item[attrname]) for item in list_to_join)
