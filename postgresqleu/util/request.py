from django.http import Http404


def get_int_or_error(reqmap, paramname, default=None):
    if paramname not in reqmap:
        if default:
            return default
        raise Http404("Parameter {} missing".format(paramname))

    p = reqmap.get(paramname)
    if not p.isnumeric():
        raise Http404("Parameter {} is not an integer".format(paramname))

    return int(p)
