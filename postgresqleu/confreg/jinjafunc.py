from django.http import Http404, HttpResponse
from django.template.backends.utils import csrf_input_lazy, csrf_token_lazy
from django.template import defaultfilters
from django.core.exceptions import ValidationError
from django.contrib.messages.api import get_messages
from django.utils.text import slugify
from django.conf import settings

import json
import os.path
import random
from itertools import groupby
from datetime import datetime, date, time
import dateutil.parser

from postgresqleu.util.context_processors import settings_context_unicode

import jinja2
import jinja2.sandbox
import markdown


from postgresqleu.confreg.templatetags.leadingnbsp import leadingnbsp

# We use a separate root directory for jinja2 templates, so find that
# directory by searching relative to ourselves.
JINJA_TEMPLATE_ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__), '../../template.jinja'))


# Locate the git revision for a repository in the given path, including
# walking up the tree to find it if the specified path is not the root.
def find_git_revision(path):
	while path != '/':
		if os.path.exists(os.path.join(path, ".git/HEAD")):
			# Found it!
			with open(os.path.join(path, '.git/HEAD')) as f:
				ref = f.readline().strip()
			if not ref.startswith('ref: refs/heads/'):
				return None
			refname = os.path.join(path, ".git/", ref[5:])
			if not os.path.isfile(refname):
				return None
			with open(refname) as f:
				fullref = f.readline()
				return fullref[:7]
		elif os.path.exists(os.path.join(path, ".deploystatic_githash")):
			with open(os.path.join(path, ".deploystatic_githash")) as f:
				return f.readline().strip()

		# Else step up one level
		path = os.path.dirname(path)
	# If no direct git hash found, search for a deploystatic file
	return None


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
	WHITELISTED_TEMPLATES=('invoices/userinvoice_spec.html',)

	def __init__(self, conference, roottemplate):
		self.conference = conference
		self.roottemplate = roottemplate
		if conference and conference.jinjadir:
			pathlist = [os.path.join(conference.jinjadir, 'templates'), JINJA_TEMPLATE_ROOT]
		else:
			pathlist = [JINJA_TEMPLATE_ROOT,]

		super(ConfTemplateLoader, self).__init__(pathlist)

	def get_source(self, environment, template):
		# Only allow loading of the root template from confreg. Everything else we allow
		# only from the conference specific directory. This is so we don't end up
		# loading a template with the wrong parameters passed to it.
		# If no conference is specified, then we allow loading all entries from the root,
		# for obvious reasons.
		if self.conference and self.conference.jinjadir and template != self.roottemplate:
			if not os.path.exists(os.path.join(self.conference.jinjadir, 'templates', template)):
				# This template may exist in pgeu, so reject it unless it's specifically
				# whitelisted as something we want to load.
				if not template in self.WHITELISTED_TEMPLATES:
					raise jinja2.TemplateNotFound(template, "Rejecting attempt to load from incorrect location")
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
	def is_safe_attribute(self, obj, attr, value):
		modname = obj.__class__.__module__

		if obj.__class__.__name__ in ('str', 'unicode') and attr == 'format':
			# We reject all format strings for now, due to
			# https://www.palletsprojects.com/blog/jinja-281-released/
			# (until we have it safely patched everywhere, *if* we need this elsewhere)
			return False

		if modname.startswith('postgresqleu.') and modname.endswith('models'):
			# This is a pgeu model. So we only allow access to the
			# ones in confreg directly.
			if not (modname.endswith('.confreg.models') or modname.endswith('confwiki.models')):
				# If the object lists a number of safe attributes,
				# then allow them and nothing else.
				if hasattr(obj, '_safe_attributes'):
					if not attr in getattr(obj, '_safe_attributes'):
						return False
				else:
					# No safe attributes specified, so assume none
					return False

			# Some objects in the confreg model are not safe, because
			# they might leak data between conferences. In general,
			# these are objects that don't have a link to a
			# conference.
			if not hasattr(obj, 'conference'):
				if hasattr(obj, '_safe_attributes'):
					# If the object lists a number of safe attributes,
					# then allow them and nothing else.
					if not attr in getattr(obj, '_safe_attributes'):
						return False
				else:
					return False
			else:
				# Has a conference, but we can still specify unsafe ones
				if hasattr(obj, '_unsafe_attributes'):
					if attr in getattr(obj, '_unsafe_attributes'):
						return False
		elif modname=='postgresqleu.invoices.util' and obj.__class__.__name__=='InvoicePresentationWrapper':
			# This is ugly, but we special-case the invoice information
			if attr in obj._unsafe_attributes:
				return False

		return super(ConfSandbox, self).is_safe_attribute(obj, attr, value)


# A couple of useful filters that we publish everywhere:

# Like |groupby, except support grouping by objects and not just by values, and sort by
# attributes on the grouped objects.
def filter_groupby_sort(objects, keyfield, sortkey):
	group = [(key, list(group)) for key, group in groupby(objects, lambda x: getattr(x, keyfield))]
	return sorted(group, key=lambda y: y[0] and getattr(y[0], sortkey) or None)

# Shuffle the order in a list, for example to randomize the order of sponsors
def filter_shuffle(l):
	try:
		r = list(l)
		random.shuffle(r)
		return r
	except:
		return l

def filter_currency_format(v):
	return u"{0} {1:,.2f}".format(unicode(settings.CURRENCY_SYMBOL, 'utf8'), v)

def filter_float_str(f, n):
	return '{{0:.{0}f}}'.format(int(n)).format(f)

# Format a datetime. If it'sa datetime, call strftime. If it's a
# string, assume it's iso format and convert it to a date first.
def filter_datetimeformat(value, fmt):
	if isinstance(value, date) or isinstance(value, datetime) or isinstance(value,time):
		return value.strftime(fmt)
	else:
		return dateutil.parser.parse(value).strftime(fmt)


# Render a conference response based on jinja2 templates configured for the conference.
# Returns the appropriate django HttpResponse object.
def render_jinja_conference_response(request, conference, pagemagic, templatename, dictionary):
	# It all starts from the base template for this conference. If it
	# does not exist, just throw a 404 early.
	if conference and conference.jinjadir and not os.path.exists(os.path.join(conference.jinjadir, 'templates/base.html')):
		raise Http404()

	env = ConfSandbox(loader=ConfTemplateLoader(conference, templatename),
					  extensions=['jinja2.ext.with_'])
	env.filters.update({
		'currency_format': filter_currency_format,
		'escapejs': defaultfilters.escapejs_filter,
		'floatstr': filter_float_str,
		'datetimeformat': filter_datetimeformat,
		'groupby_sort': filter_groupby_sort,
		'leadingnbsp': leadingnbsp,
		'markdown': lambda t: jinja2.Markup(markdown.markdown(t, extensions=['tables',])),
		'shuffle': filter_shuffle,
		'slugify': slugify,
		'yesno': lambda b,v: v.split(',')[not b],
	})

	# If ?test=1 is specified, try to load a template with .test in the
	# name.
	if request.GET.get('test', None) == '1':
		templatename = templatename + '.test'
	t = env.get_template(templatename)

	# Optionally load the JSON context with template-specific data
	if conference and conference.jinjadir and os.path.exists(os.path.join(conference.jinjadir, 'templates/context.json')):
		try:
			with open(os.path.join(conference.jinjadir, 'templates/context.json')) as f:
				c = json.load(f)
		except ValueError, e:
			return HttpResponse("JSON parse failed: {0}".format(e), content_type="text/plain")
		except Exception:
			c = {}
	else:
		c = {}

	if request.user and request.user.is_authenticated():
		fullname = u'{0} {1}'.format(request.user.first_name, request.user.last_name)
		email = request.user.email
	else:
		fullname = None
		email = None
	c.update({
		'pgeu_hosted': True,
		'now': datetime.now(),
		'conference': conference,
		'pagemagic': pagemagic,
		'username': request.user and request.user.username or None,
		'userfullname': fullname,
		'useremail': email,
		'csrf_input': csrf_input_lazy(request),
		'csrf_token': csrf_token_lazy(request),
		'messages': get_messages(request),
	})
	if conference and conference.jinjadir:
		c['githash'] = find_git_revision(conference.jinjadir)


	if dictionary:
		c.update(dictionary)

	# For local testing, there may also be a context.override.json
	if conference and conference.jinjadir and os.path.exists(os.path.join(conference.jinjadir, 'templates/context.override.json')):
		try:
			with open(os.path.join(conference.jinjadir, 'templates/context.override.json')) as f:
				c.update(json.load(f))
		except Exception:
			pass

	c.update(settings_context_unicode())

	return HttpResponse(t.render(**c), content_type='text/html')





# Small sandboxed jinja templates that can be configured in system
def render_sandboxed_template(templatestr, context):
	env = ConfSandbox(loader=jinja2.DictLoader({'t': templatestr}))
	t = env.get_template('t')
	return t.render(context)

class JinjaTemplateValidator(object):
	def __init__(self, context={}):
		self.context = context

	def __call__(self, s):
		try:
			render_sandboxed_template(s, self.context)
		except jinja2.TemplateSyntaxError, e:
			raise ValidationError("Template syntax error: %s" % e)
		except Exception, e:
			raise ValidationError("Failed to parse template: %s" % e)
