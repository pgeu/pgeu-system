from django.http import Http404


def get_int_or_error(reqmap, paramname, default=None, allow_negative=False):
    if paramname not in reqmap:
        if default:
            return default
        raise Http404("Parameter {} missing".format(paramname))

    p = reqmap.get(paramname)
    if allow_negative and p.startswith('-'):
        p = p[1:]
        negative = -1
    else:
        negative = 1

    if not p.isnumeric():
        raise Http404("Parameter {} is not an integer".format(paramname))

    return int(p) * negative
