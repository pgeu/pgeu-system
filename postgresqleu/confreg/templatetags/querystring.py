from django import template

register = template.Library()


@register.simple_tag
def edit_querystring(request, *args):
    i = iter(args)
    updated = request.GET.copy()
    for k, v in zip(i, i):
        updated[k] = v
    return updated.urlencode()
