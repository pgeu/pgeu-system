from django.conf import settings

import os
import json
import logging
import copy

try:
    from postgresqleu.util.context_processors import settings_context
except ImportError:
    # When running standalone jinjapdf, we will fail to import the global settings,
    # so in this case just set it to empty.
    def settings_context():
        return {}

try:
    import yaml
    has_yaml = True
except ImportError:
    has_yaml = False


# XXX: keep in sync with deploystatic.py!
def deep_update_context(target, source):
    for k, v in source.items():
        if type(v) == dict:
            # If this is a dict stored in the dict
            if k not in target:
                # Target didn't have it, so copy it over
                target[k] = copy.deepcopy(v)
            elif type(target[k]) != dict:
                # Target had something but it's not a dict, so overwrite it
                target[k] = copy.deepcopy(v)
            else:
                deep_update_context(target[k], v)
        else:
            target[k] = copy.copy(v)


def _load_context_file(filename, ignore_exceptions=True):
    try:
        with open(filename, encoding='utf8') as f:
            if filename.endswith('.json'):
                return json.load(f)
            else:
                return yaml.safe_load(f)
    except ValueError as e:
        # Malformatted JSON -- pass it through as an exception
        raise
    except Exception:
        if not ignore_exceptions:
            raise
        return {}


def load_base_context(rootdir):
    c = {}
    if os.path.isfile(os.path.join(rootdir, 'templates/context.json')):
        deep_update_context(c, _load_context_file(os.path.join(rootdir, 'templates/context.json')))
    if has_yaml and os.path.isfile(os.path.join(rootdir, 'templates/context.yaml')):
        deep_update_context(c, _load_context_file(os.path.join(rootdir, 'templates/context.yaml')))
    return c


def load_override_context(rootdir):
    # Load contexts in override directory, if any
    c = {}
    if os.path.isdir(os.path.join(rootdir, 'templates/context.override.d')):
        for fn in sorted(os.listdir(os.path.join(rootdir, 'templates/context.override.d'))):
            if fn.endswith('.json') or (has_yaml and fn.endswith('.yaml')):
                try:
                    deep_update_context(c, _load_context_file(os.path.join(rootdir, 'templates/context.override.d', fn), False))
                except Exception as e:
                    logging.getLogger(__name__).warning(
                        'Failed to load context file {}: {}'.format(os.path.join(rootdir, 'templates/context.override.d', fn), e)
                    )
    return c


def update_with_override_context(context, rootdir):
    deep_update_context(context, load_override_context(rootdir))


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


def load_all_context(conference, inject, dictionary=None):
    if conference and conference.jinjaenabled and conference.jinjadir:
        try:
            c = load_base_context(conference.jinjadir)
        except ValueError as e:
            return HttpResponse("JSON parse failed: {0}".format(e), content_type="text/plain")
    else:
        c = {}

    c.update(inject)

    if conference and conference.jinjaenabled and conference.jinjadir:
        c['githash'] = find_git_revision(conference.jinjadir)

    if dictionary:
        c.update(dictionary)

    if conference and conference.jinjaenabled and conference.jinjadir:
        update_with_override_context(c, conference.jinjadir)

    c.update(settings_context())

    if conference:
        c['confbase'] = '{}/events/{}'.format(settings.SITEBASE, conference.urlname)

    return c
