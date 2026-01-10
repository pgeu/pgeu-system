from django.http import Http404, HttpResponse, HttpResponseNotModified
from django.template.backends.utils import csrf_input_lazy, csrf_token_lazy
from django.template import defaultfilters
from django.core.exceptions import ValidationError, FieldDoesNotExist
from django.contrib.messages.api import get_messages
from django.utils.text import slugify
from django.utils.timesince import timesince
from django.utils import timezone
from django.conf import settings
import django.db.models

import os.path
import random
from itertools import groupby
from datetime import datetime, date, time
import dateutil.parser
import textwrap
from Cryptodome.Hash import SHA

from postgresqleu.confreg.templatetags.currency import format_currency
from postgresqleu.confreg.templatetags.leadingnbsp import leadingnbsp
from postgresqleu.confreg.templatetags.formutil import field_class
from postgresqleu.util.templatetags import svgcharts
from postgresqleu.util.templatetags.assets import do_render_asset
from postgresqleu.util.messaging import get_messaging_class_from_typename
from postgresqleu.util.markup import pgmarkdown

import markupsafe
import jinja2
import jinja2.sandbox
try:
    from jinja2 import pass_context
except ImportError:
    # Try Jinja2 2.x version
    from jinja2 import contextfilter as pass_context

from .contextutil import load_all_context

# We use a separate root directory for jinja2 templates, so find that
# directory by searching relative to ourselves.
JINJA_TEMPLATE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../template.jinja'))


def _get_conference_pathlist(conference, disableconferencetemplates):
    pathlist = []
    if conference and conference.jinjaenabled and conference.jinjadir and not disableconferencetemplates:
        pathlist.append(os.path.join(conference.jinjadir, 'templates'))
    if getattr(settings, 'SYSTEM_SKIN_DIRECTORY', False):
        pathlist.append(os.path.join(settings.SYSTEM_SKIN_DIRECTORY, 'template.jinja'))
    pathlist.append(JINJA_TEMPLATE_ROOT)
    return pathlist


#
# A template loader specifically for confreg. It will
#  - load user-supplied templates from the specified conferences's
#    <jinjadir>/templates (and subdirectories)
#  - the specified template from the confreg namespace (but *not* other templates
#    in the conference namespace)
#  - specific whitelisted templates elsewhere
#
# This will make it impossible for a user-supplied templates to "break out"
# by including or inheriting templates from other parts of the system.
class ConfTemplateLoader(jinja2.FileSystemLoader):
    # Templates that are whitelisted for inclusion.
    WHITELISTED_TEMPLATES = ('invoices/userinvoice_spec.html', 'mailbase.html', 'mailinline.css', 'confreg/mailbase.html', 'confreg/mailinline.css', 'confsponsor/mailbase.html')

    def __init__(self, conference, roottemplate, disableconferencetemplates=False):
        self.conference = conference
        self.roottemplate = roottemplate
        self.disableconferencetemplates = disableconferencetemplates

        pathlist = _get_conference_pathlist(conference, disableconferencetemplates)

        # Process it all with os.fspath. That's what the inherited
        # FileSystemLoader does, but we also need the ability to
        # override it in get_source() so we do it as well.
        self.pathlist = [os.fspath(p) for p in pathlist]
        self.cutlevel = 0

        super(ConfTemplateLoader, self).__init__(self.pathlist)

    def get_source(self, environment, template):
        # Only allow loading of the root template from confreg. Everything else we allow
        # only from the conference specific directory. This is so we don't end up
        # loading a template with the wrong parameters passed to it.
        # If no conference is specified, then we allow loading all entries from the root,
        # for obvious reasons.
        if self.conference and self.conference.jinjaenabled and self.conference.jinjadir and template != self.roottemplate:
            if not os.path.exists(os.path.join(self.conference.jinjadir, 'templates', template)):
                # This template may exist in pgeu, so reject it unless it's specifically
                # whitelisted as something we want to load.
                if template not in self.WHITELISTED_TEMPLATES:
                    raise jinja2.TemplateNotFound(template, "Rejecting attempt to load from incorrect location: {}".format(template))
        if self.cutlevel:
            # Override the searchpath to drop one or more levels, to
            # handle inheritance of "the same template"
            self.searchpath = self.pathlist[self.cutlevel:]
        else:
            self.searchpath = self.pathlist
        return super(ConfTemplateLoader, self).get_source(environment, template)


#
# A jinja2 sandbox for rendering confreg templates.
#
# It's designed for confreg only, and as such applies a number of restrictions on
# which attributes can be accessed of the objects that's passed to it.
#
# - Restrictions are applied to all pgeu models:
#   - For any models outside the confreg and confwiki namespaces, only attributes
#     specifically listed in the models _safe_attributes are allowed.
#   - The same applies to any model wihin confreg that has a _safe_attributes set
#   - Any model that has a member named conference are considered part of confreg,
#     and access will be allowed to all attributes on it.
#     - Except if it has a member called _unsafe_attributes, in which case they are
#       restricted.
#   - Specifically for InvoicePresentationWrapper, access is allowed except for
#     things listed in _unsafe_attributes.
#
# For all other access, the jinja2 default sandbox rules apply.
#
class ConfSandbox(jinja2.sandbox.SandboxedEnvironment):
    def __init__(self, *args, **kwargs):
        # We have to disable the cache for our extend-from-parent support, since the cache key
        # for confreg/foo.html would become the same regardless of if the template is from the
        # base, from the skin or from the conference. Given that we currently recreate the
        # environment once for each request, the caching doesn't really make any difference
        # anyway. Should we in the future want to use the caching, we have to take this into
        # account though.
        super().__init__(*args, cache_size=0, **kwargs)

    def get_template(self, name, parent=None, globals=None):
        if name == parent:
            self.loader.cutlevel += 1
        else:
            self.loader.cutlevel = 0
        return super().get_template(name, parent, globals)

    def is_safe_attribute(self, obj, attr, value):
        modname = obj.__class__.__module__

        if obj.__class__.__name__ in ('str', 'unicode') and attr in ('format', 'format_map'):
            # We reject all format strings for now, due to
            # https://www.palletsprojects.com/blog/jinja-281-released/
            # (until we have it safely patched everywhere, *if* we need this elsewhere)
            return False

        if modname.startswith('postgresqleu.') and modname.endswith('models'):
            # This is a pgeu model. So we only allow access to the
            # ones in confreg directly.
            if not (modname.endswith('.confreg.models') or modname.endswith('.confwiki.models')):
                # If the object lists a number of safe attributes,
                # then allow them and nothing else.
                if hasattr(obj, '_safe_attributes'):
                    if attr not in getattr(obj, '_safe_attributes'):
                        return False
                else:
                    # No safe attributes specified, so assume none
                    return False

            # Some objects in the confreg model are not safe, because
            # they might leak data between conferences. In general,
            # these are objects that don't have a link to a
            # conference.
            try:
                obj._meta.get_field('conference')
                # Has a conference, but we can still specify unsafe ones
                if hasattr(obj, '_unsafe_attributes'):
                    if attr in getattr(obj, '_unsafe_attributes'):
                        return False
            except FieldDoesNotExist:
                # No conference field on this model. If it has a list of safe attributes, allow the field
                # if it's in there, otherwise reject all.
                if hasattr(obj, '_safe_attributes'):
                    # If the object lists a number of safe attributes,
                    # then allow them and nothing else.
                    if attr not in getattr(obj, '_safe_attributes'):
                        return False
                else:
                    return False
        elif modname == 'postgresqleu.invoices.util' and obj.__class__.__name__ == 'InvoicePresentationWrapper':
            # This is ugly, but we special-case the invoice information
            if attr in obj._unsafe_attributes:
                return False

        return super(ConfSandbox, self).is_safe_attribute(obj, attr, value)


# Enumerate all available attributes (in the postgresqleu scope), showing their
# availability.
def get_all_available_attributes(objclass, depth=0):
    if depth > 5:
        # We just cap it here to avoid infinitely recursing through trees
        return

    modname = objclass.__module__
    if not (modname.startswith('postgresqleu.') and modname.endswith('models')):
        # Outside of models, we also specifically allow the InvoicePresentationWrapper
        if modname != 'postgresqleu.invoices.util' or objclass.__name__ != 'InvoicePresentationWrapper':
            return

    for attname, attref in objclass.__dict__.items():
        def _is_visible():
            # Implement the same rules as above, because reusing the sandbox is painful as it
            # works with objects and not models.
            if attname in getattr(objclass, '_unsafe_attributes', []):
                return False
            if hasattr(objclass, '_safe_attributes'):
                return attname in getattr(objclass, '_safe_attributes')
            # If neither safe nor unsafe is specified, we only allow access if the model has
            # a conference field specified.
            return hasattr(objclass, 'conference')
        if issubclass(type(attref), django.db.models.query_utils.DeferredAttribute):
            if _is_visible():
                yield attname, attref.field.verbose_name
        elif issubclass(type(attref), django.db.models.fields.related_descriptors.ForwardManyToOneDescriptor):
            # Special case, don't recurse into conference model if we're not at the top object (to keep smaller)
            if attname == 'conference' and depth > 0:
                continue
            if _is_visible():
                yield attname, dict(get_all_available_attributes(type(attref.field.related_model()), depth + 1))
        elif issubclass(type(attref), django.db.models.fields.related_descriptors.ManyToManyDescriptor) and not attref.reverse:
            if _is_visible():
                yield attname, [dict(get_all_available_attributes(type(attref.field.related_model()), depth + 1))]


# A couple of useful filters that we publish everywhere:

# Like |groupby, except support grouping by objects and not just by values, and sort by
# attributes on the grouped objects.
def filter_groupby_sort(objects, keyfield, sortkey):
    group = [(key, list(group)) for key, group in groupby(objects, lambda x: getattr(x, keyfield))]
    return sorted(group, key=lambda y: y[0] and getattr(y[0], sortkey) or 0)


# Shuffle the order in a list, for example to randomize the order of sponsors
def filter_shuffle(thelist):
    try:
        r = list(thelist)
        random.shuffle(r)
        return r
    except Exception as e:
        return thelist


def filter_float_str(f, n):
    return '{{0:.{0}f}}'.format(int(n)).format(f)


# Format a datetime. If it's a datetime, call strftime. If it's a
# string, assume it's iso format and convert it to a date first.
def filter_datetimeformat(value, fmt):
    if isinstance(value, date) or isinstance(value, datetime) or isinstance(value, time):
        if isinstance(value, datetime) and timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime(fmt)
    else:
        return dateutil.parser.parse(value).strftime(fmt)


# Take a multiline text and turn it into what's needed to create a multiline svg text
# using <tspan>. Linebreak at <linelength> characters.
def filter_svgparagraph(value, linelength, x, y, dy, parady):
    def _svgparagraph():
        for j, p in enumerate(value.split("\n")):
            for i, l in enumerate(textwrap.wrap(p, width=linelength, expand_tabs=False)):
                _dy = dy
                if i == 0 and j != 0:
                    _dy += parady
                yield '<tspan x="{}" dy="{}">{}</tspan>'.format(x, _dy, jinja2.escape(l))

    return '<text x="{}" y="{}">{}</text>'.format(x, y, "\n".join(_svgparagraph()))


@pass_context
def filter_applymacro(context, obj, macroname):
    return context.resolve(macroname)(obj)


@pass_context
def filter_lookup(context, name, default=None):
    if not name:
        if default is not None:
            return default
        raise KeyError("No key specified")

    c = context
    parts = name.split('.')
    while parts:
        p = parts.pop(0)
        if p not in c:
            if default is not None:
                return default
            raise KeyError("Key {} not found".format(name))
        c = c[p]
    return str(c)


# Unpack a social media link for the specific social media being rendered for.
# This filter is *not* enabled by default.
@pass_context
def filter_social(context, attr):
    if not context.get('messaging', None):
        return None
    name = context['messaging'].typename.lower()
    return getattr(attr, 'social', {}).get(name, None)


# Get social media profiles including links from a structure.
# Returns a list of (provider, handle, link) for each configured
# social media identity.
@pass_context
def filter_social_links(context, attr):
    if attr:
        for k, v in attr.items():
            m = get_messaging_class_from_typename(k)
            if m:
                yield (k, v, m.get_link_from_identifier(v))


# Inline CSS using pynliner, if available
@pass_context
def filter_inlinecss(context, contents, cssname):
    try:
        import pynliner
    except ImportError:
        print("CSS inlining not supported withut pynliner!")
        return contents

    css = render_jinja_conference_template(context['conference'], cssname, context)
    p = pynliner.Pynliner().from_string(contents)
    p.with_cssString(css)
    return p.run()


extra_filters = {
    'format_currency': format_currency,
    'escapejs': defaultfilters.escapejs_filter,
    'field_class': field_class,
    'floatstr': filter_float_str,
    'datetimeformat': filter_datetimeformat,
    'timesince': timesince,
    'groupby_sort': filter_groupby_sort,
    'leadingnbsp': leadingnbsp,
    'markdown': lambda t: markupsafe.Markup(pgmarkdown(t)),
    'shuffle': filter_shuffle,
    'slugify': slugify,
    'yesno': lambda b, v: v.split(',')[not b],
    'wordwraptolist': lambda t, w: textwrap.wrap(t, width=w, expand_tabs=False),
    'svgparagraph': filter_svgparagraph,
    'applymacro': filter_applymacro,
    'lookup': filter_lookup,
    'social_links': filter_social_links,
    'inlinecss': filter_inlinecss,
}

extra_globals = {
    'svgcharts': svgcharts,
}


# We can resolve assets only when the template is in our main site. Anything running with
# deploystatic is going to have to solve this outside anyway. That means we can safely
# reference internal functions.
def _resolve_asset(assettype, assetname):
    return do_render_asset(assettype, assetname)


def _get_jinja_conference_template(conference, templatename, dictionary, disableconferencetemplates=False, renderglobals={}):
    # It all starts from the base template for this conference. If it
    # does not exist, just throw a 404 early.
    if conference and conference.jinjaenabled and conference.jinjadir and not os.path.exists(os.path.join(conference.jinjadir, 'templates/base.html')):
        raise Http404()

    if jinja2.__version__ > '3.1':
        extensions = []
    else:
        extensions = ['jinja2.ext.with_']
    env = ConfSandbox(
        loader=ConfTemplateLoader(conference, templatename, disableconferencetemplates=disableconferencetemplates),
        extensions=extensions,
    )
    env.filters.update(extra_filters)
    env.globals.update(extra_globals)
    env.globals.update(renderglobals)

    t = env.get_template(templatename)

    c = load_all_context(conference,
                         {
                             'pgeu_hosted': True,
                             'now': timezone.now(),
                             'conference': conference,
                             'asset': _resolve_asset,
                         },
                         dictionary)

    return t, c


def render_jinja_conference_template(conference, templatename, dictionary, disableconferencetemplates=False):
    t, c = _get_jinja_conference_template(conference, templatename, dictionary, disableconferencetemplates=False)
    return t.render(**c)


def render_jinja_template(templatename, dictionary):
    return render_jinja_conference_template(None, templatename, dictionary, True)


def _get_contenttype_from_extension(f):
    _map = {
        'png': 'image/png',
        'jpg': 'image/jpeg',
    }
    e = os.path.splitext(f)[1][1:]
    if e not in _map:
        raise Exception("Unknown extension {}".format(e))
    return _map[e]


def render_jinja_conference_mail(conference, templatename, dictionary, subject):
    templatename, templateext = os.path.splitext(templatename)
    if templateext not in ('.txt', '.md', '.mail'):
        raise Exception("Invalid mail template extension")

    dictionary['subject'] = subject

    class Attachments:
        def __init__(self):
            self.attachments = {}

        def register(self, context, name, filename):
            self.attachments[name] = filename
            return ''

    renderglobals = {
        'attachments': Attachments(),
    }

    # Find the root template(s) to render.
    for p in _get_conference_pathlist(conference, False):
        if os.path.isfile(os.path.join(p, templatename + '.txt')):
            if os.path.isfile(os.path.join(p, templatename + '.html')):
                # Both HTML and TXT exists, so render as separate parts
                txtpart = render_jinja_conference_template(conference, templatename + '.txt', dictionary)
                htmltempl, htmlctx = _get_jinja_conference_template(conference, templatename + '.html', dictionary, renderglobals=renderglobals)
            else:
                # TXT exists, but not HTML, so render as markdown inside base template
                # Extract the first line to be the "greeting" part of the email in the HTML template.
                txtpart = render_jinja_conference_template(conference, templatename + '.txt', dictionary)
                contentlines = txtpart.splitlines()
                htmltempl, htmlctx = _get_jinja_conference_template(
                    conference,
                    conference and 'confreg/mailbase.html' or 'mailbase.html',
                    {
                        'subject': subject,
                        'greeting': contentlines[0],
                        'content': markupsafe.Markup(pgmarkdown("\n".join(contentlines[1:]))),
                    },
                    renderglobals=renderglobals,
                )
            # If there are any attachments here they should've been specified in a block, so we read
            # it out of there.
            htmlpart = htmltempl.render(**htmlctx)
            attachments = []
            for name, filename in renderglobals['attachments'].attachments.items():
                # Find the filename in the template directory structure
                for p in _get_conference_pathlist(conference, False):
                    if os.path.isfile(os.path.join(p, filename)):
                        with open(os.path.join(p, filename), 'rb') as f:
                            attachments.append((name, _get_contenttype_from_extension(name), f.read()))
                            break
            return (txtpart, htmlpart, attachments)
        else:
            # TXT does not exist, so we ignore and move on to the next level
            pass

    # This should maybe not be Http404, but for consistency...
    raise Http404("Mail template not found")


# Render a conference response based on jinja2 templates configured for the conference.
# Returns the appropriate django HttpResponse object.
def render_jinja_conference_response(request, conference, pagemagic, templatename, dictionary):
    # If ?test=1 is specified, try to load a template with .test in the
    # name.
    if request.GET.get('test', None) == '1':
        templatename = templatename + '.test'

    d = {
        'pagemagic': pagemagic,
        'csrf_input': csrf_input_lazy(request),
        'csrf_token': csrf_token_lazy(request),
        'messages': get_messages(request),
    }

    if request.user and request.user.is_authenticated:
        d.update({
            'username': request.user.username,
            'userfullname': '{0} {1}'.format(request.user.first_name, request.user.last_name),
            'useremail': request.user.email,
        })
    else:
        d.update({
            'username': None,
            'userfullname': None,
            'useremail': None,
        })
    if dictionary:
        d.update(dictionary)

    try:
        r = HttpResponse(render_jinja_conference_template(conference, templatename, d))
    except jinja2.exceptions.TemplateError as e:
        # If we have a template syntax error in a conference template, retry without it.
        r = HttpResponse(render_jinja_conference_template(conference, templatename, d, disableconferencetemplates=True))
        r['X-Conference-Template-Error'] = str(e)

    r.content_type = 'text/html'
    return r


def render_jinja_conference_svg(request, conference, cardformat, templatename, dictionary):
    svg = render_jinja_conference_template(conference, templatename, dictionary)
    if cardformat == 'svg':
        return HttpResponse(svg, 'image/svg+xml')
    else:
        try:
            import cairosvg
        except ImportError:
            # No cairosvg available, so just 404 on this.
            raise Http404()

        # Since turning SVG into PNG is a lot more expensive than just rendering the SVG,
        # generate an appropriate ETag for it, and verify that one.
        etag = '"{}"'.format(SHA.new(svg.encode('utf8')).hexdigest())

        if request.META.get('HTTP_IF_NONE_MATCH', None) == etag:
            return HttpResponseNotModified()

        r = HttpResponse(cairosvg.svg2png(svg), content_type='image/png')
        r['ETag'] = etag
        return r


# Small sandboxed jinja templates that can be configured in system
def render_sandboxed_template(templatestr, context, filters=None):
    env = ConfSandbox(loader=jinja2.DictLoader({'t': templatestr}))
    env.filters.update(extra_filters)
    if filters:
        env.filters.update(filters)
    t = env.get_template('t')
    return t.render(context)


class JinjaTemplateValidator(object):
    def __init__(self, context={}, filters=None):
        self.context = context
        self.filters = filters

    def __call__(self, s):
        try:
            render_sandboxed_template(s, self.context, self.filters)
        except jinja2.TemplateSyntaxError as e:
            raise ValidationError("Template syntax error: %s" % e)
        except Exception as e:
            raise ValidationError("Failed to parse template: %s" % e)
