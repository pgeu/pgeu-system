from django import template
from django.utils.safestring import mark_safe
from django.conf import settings

register = template.Library()


@register.simple_tag
def asset(assettype, assetname):
    return mark_safe(do_render_asset(assettype, assetname))


def do_render_asset(assettype, assetname):
    if assetname not in settings.ASSETS:
        return "<!-- invalid asset reference -->"
    if assettype not in settings.ASSETS[assetname]:
        return "<!-- invalid asset type reference -->"

    asset = settings.ASSETS[assetname][assettype]

    if isinstance(asset, (str, dict)):
        return _render_asset(assettype, asset)
    elif isinstance(asset, (list, tuple)):
        return " ".join(
            _render_asset(assettype, a) for a in asset
        )
    else:
        raise Exception("Unknown asset config for {}/{}".format(assetname, assettype))


def _render_asset(assettype, asset):
    if assettype == "css":
        if isinstance(asset, str):
            return mark_safe('<link rel="stylesheet" crossorigin="anonymous" href="{}">'.format(asset))
        else:
            return mark_safe('<link rel="stylesheet" crossorigin="anonymous" href="{}" integrity="{}">'.format(*list(asset.items())[0]))
    elif assettype == "js":
        if isinstance(asset, str):
            return mark_safe('<script crossorigin="anonymous" src="{}"></script>'.format(asset))
        else:
            return mark_safe('<script crossorigin="anonymous" src="{}" integrity="{}"></script>'.format(*list(asset.items())[0]))

    # Should never happen since we looked it up in settings
    raise Exception("Unknown asset type {}".format(assettype))
