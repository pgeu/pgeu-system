#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Deploy a static site based on jinja2 templates (sandboxed)

import argparse
import sys
import os
import os.path
import filecmp
import shutil
import json
import random
import re
import unicodedata
import io
import subprocess
import tarfile
import copy

import jinja2
import jinja2.sandbox

import markdown

from datetime import datetime, date, time
import dateutil.parser


#
# Some useful filters. We include them inline in this file to make it
# standalone useful.
#
# Like |groupby, except support grouping by objects and not just by values, and sort by
# attributes on the grouped objects.
def filter_groupby_sort(objects, keyfield, sortkey):
    group = [(key, list(group)) for key, group in groupby(objects, lambda x: getattr(x, keyfield))]
    return sorted(group, key=lambda y: y[0] and getattr(y[0], sortkey) or 0)


# Shuffle the order in a list, for example to randomize the order of sponsors
def filter_shuffle(l):
    try:
        r = list(l)
        random.shuffle(r)
        return r
    except Exception as e:
        return l


# Format a datetime. If it's a datetime, call strftime. If it's a
# string, assume it's iso format and convert it to a date first.
def filter_datetimeformat(value, fmt):
    if isinstance(value, date) or isinstance(value, datetime) or isinstance(value, time):
        return value.strftime(fmt)
    else:
        return dateutil.parser.parse(value).strftime(fmt)


# Slugify a text
def filter_slugify(value):
    if not value:
        return ''
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    return re.sub(r'[-\s]+', '-', value)


global_filters = {
    'groupby_sort': filter_groupby_sort,
    'shuffle': filter_shuffle,
    'slugify': filter_slugify,
    'datetimeformat': filter_datetimeformat,
    'markdown': lambda t: jinja2.Markup(markdown.markdown(t)),
}


# Extend the default jinja sandbox
class DeploySandbox(jinja2.sandbox.SandboxedEnvironment):
    def is_safe_attribute(self, obj, attr, value):
        if obj.__class__.__name__ in ('str', 'unicode') and attr in ('format', 'format_map'):
            # We reject all format strings for now, due to
            # https://www.palletsprojects.com/blog/jinja-281-released/
            # (until we have it safely patched everywhere, *if* we need this elsewhere)
            return False

        return super(DeploySandbox, self).is_safe_attribute(obj, attr, value)


# Wrap operations on a generic directory
class SourceWrapper(object):
    def __init__(self, root):
        self.root = root

    def isdir(self, d):
        return os.path.isdir(os.path.join(self.root, d))

    def walkfiles(self, d):
        relroot = os.path.join(self.root, d)
        for dn, subdirs, filenames in os.walk(relroot):
            relpath = os.path.relpath(dn, self.root)
            for fn in filenames:
                yield (relpath, fn)

    def listfiles(self, d):
        if os.path.isdir(os.path.join(self.root, d)):
            return os.listdir(os.path.join(self.root, d))
        return []

    def copy_if_changed(self, relsource, fulldest):
        fullsrc = os.path.join(self.root, relsource)
        if (not os.path.exists(fulldest)) or (not filecmp.cmp(fullsrc, fulldest)):
            shutil.copy2(fullsrc, fulldest)

    def readfile(self, src):
        if os.path.isfile(os.path.join(self.root, src)):
            with open(os.path.join(self.root, src), "rb") as f:
                return f.read()
        else:
            return None


# Wrap operations on a tarfile
class TarWrapper(object):
    def __init__(self, tarstream):
        self.tardata = io.BytesIO()
        shutil.copyfileobj(tarstream, self.tardata)
        self.tardata.seek(0)
        self.tarfile = tarfile.open(fileobj=self.tardata)

        self.tarstruct = {}
        for m in self.tarfile.getmembers():
            self.tarstruct[m.name] = m

    def isdir(self, d):
        return d in self.tarstruct and self.tarstruct[d].isdir()

    def isfile(self, f):
        return f in self.tarstruct and self.tarstruct[f].isfile()

    def readfile(self, src):
        if src in self.tarstruct and self.tarstruct[src].isfile():
            return self.tarfile.extractfile(src).read()
        else:
            return None

    def walkfiles(self, d):
        for k in self.tarstruct.keys():
            if k.startswith(d + '/') and self.tarstruct[k].isfile():
                yield (os.path.dirname(k), os.path.basename(k))

    def listfiles(self, d):
        for k in self.tarstruct.keys():
            if os.path.dirname(k) == d:
                yield os.path.basename(k)

    def copy_if_changed(self, relsource, fulldest):
        sourcedata = self.readfile(relsource)

        if os.path.isfile(fulldest):
            with open(fulldest, 'rb') as f:
                x = f.read()
                if x == sourcedata:
                    return

        with open(fulldest, 'wb') as f:
            f.write(sourcedata)


class JinjaTarLoader(jinja2.BaseLoader):
    def __init__(self, tarwrapper):
        self.tarwrapper = tarwrapper

    def get_source(self, environment, template):
        t = os.path.join('templates/', template)
        if self.tarwrapper.isfile(t):
            return (self.tarwrapper.readfile(t).decode('utf8'), None, None)
        raise jinja2.TemplateNotFound(template)


# Optionally load a JSON context
def load_context(jsondata):
    if jsondata:
        return json.loads(jsondata.decode('utf8'))
    else:
        return {}


# XXX: keep in sync with confreg/contextutil.py
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


# Locate which git revision we're on
def find_git_revision(path):
    while path != '/':
        if os.path.exists(os.path.join(path, ".git/HEAD")):
            # Found it!
            with open(os.path.join(path, '.git/HEAD')) as f:
                ref = f.readline().strip()
            if not ref.startswith('ref: refs/heads/'):
                print("Invalid git reference {0}".format(ref))
                return None
            refname = os.path.join(path, ".git/", ref[5:])
            if not os.path.isfile(refname):
                print("Could not find git ref {0}".format(refname))
                return None
            with open(refname) as f:
                fullref = f.readline()
                return fullref[:7]
        # Else step up one level
        path = os.path.dirname(path)
    return None


# Actual deployment function
def deploy_template(env, template, destfile, context):
    t = env.get_template(template)
    try:
        s = t.render(**context)
    except jinja2.exceptions.TemplateSyntaxError as e:
        print("ERROR: Jinja template syntax error in {}: {}".format(template, e))
        sys.exit(1)

    # Only write the file if it has actually changed
    if os.path.isfile(destfile):
        with open(destfile, encoding="utf8") as f:
            if f.read() == s:
                return

    with open(destfile, 'w', encoding="utf8") as f:
        f.write(s)


def _deploy_static(source, destpath):
    knownfiles = []
    # We could use copytree(), but we need to know which files are there so we can
    # remove old files, so we might as well do the full processing this way.
    for relpath, relname in source.walkfiles('static'):
        if not os.path.isdir(os.path.join(destpath, relpath)):
            os.makedirs(os.path.join(destpath, relpath))

        relsource = os.path.join(relpath, relname)
        source.copy_if_changed(relsource, os.path.join(destpath, relsource))

        knownfiles.append(relsource)
    return knownfiles


def _get_all_parent_directories(dirlist):
    for d in dirlist:
        while d:
            d = os.path.dirname(d)
            if d:
                yield d


def remove_unknown(knownfiles, destpath):
    # Build a list of known directories. This includes any directories with
    # files in them, but also parents of any such directories (recursively).
    knowndirs = set([os.path.dirname(f) for f in knownfiles])

    knowndirs.update([d for d in _get_all_parent_directories(knowndirs) if d not in knowndirs])

    for dn, subdirs, filenames in os.walk(destpath):
        relpath = os.path.relpath(dn, destpath)
        if relpath == '.':
            relpath = ''
        for fn in filenames:
            f = os.path.join(relpath, fn)
            if f not in knownfiles:
                os.unlink(os.path.join(destpath, f))
        for dn in subdirs:
            d = os.path.join(relpath, dn)
            if d not in knowndirs:
                # Remove directory recursively, since there can be nothing left
                # in it.
                shutil.rmtree(os.path.join(destpath, d))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Deploy jinja based static site')
    parser.add_argument('sourcepath', type=str, help='Source path')
    parser.add_argument('destpath', type=str, help='Destination path')
    parser.add_argument('--branch', type=str, help='Deploy directly from branch')
    parser.add_argument('--templates', action='store_true', help='Deploy templates (except pages) and static instead of pages')

    args = parser.parse_args()

    if not os.path.isabs(args.sourcepath):
        print("Source path is not absolute!")
        sys.exit(1)
    if not os.path.isabs(args.destpath):
        print("Destination path is not absolute!")
        sys.exit(1)

    if not os.path.isdir(args.sourcepath):
        print("Source directory does not exist!")
        sys.exit(1)

    if not os.path.isdir(args.destpath):
        print("Destination directory does not exist!")
        sys.exit(1)

    if args.branch:
        s = subprocess.Popen(['/usr/bin/git', 'archive', '--format=tar', args.branch],
                             stdout=subprocess.PIPE,
                             cwd=args.sourcepath)
        source = TarWrapper(s.stdout)
        s.stdout.close()
        s = subprocess.Popen(['/usr/bin/git', 'rev-parse', '--short', args.branch],
                             stdout=subprocess.PIPE,
                             cwd=args.sourcepath)
        git_revision = s.stdout.readline().strip().decode('ascii')
        s.stdout.close()
    else:
        source = SourceWrapper(args.sourcepath)
        git_revision = find_git_revision(args.sourcepath)

    for d in ('templates', 'templates/pages', 'static'):
        if not source.isdir(d):
            print("'{0}' subdirectory does not exist in source!".format(d))
            sys.exit(1)

    if args.templates:
        # Just deploy templates. They are simply copied over, for use by backend
        # system.
        knownfiles = []
        for relpath, relname in source.walkfiles('templates'):
            if relpath.startswith('templates/pages'):
                continue

            if not os.path.isdir(os.path.join(args.destpath, relpath)):
                os.makedirs(os.path.join(args.destpath, relpath))

            relsource = os.path.join(relpath, relname)
            source.copy_if_changed(relsource, os.path.join(args.destpath, relsource))

            knownfiles.append(relsource)

        knownfiles.extend(_deploy_static(source, args.destpath))

        remove_unknown(knownfiles, args.destpath)

        # Generate a githash file
        with open(os.path.join(args.destpath, ".deploystatic_githash"), "w") as f:
            f.write(git_revision)

        sys.exit(0)

    # Set up jinja environment
    if args.branch:
        env = DeploySandbox(loader=JinjaTarLoader(source))
    else:
        env = DeploySandbox(loader=jinja2.FileSystemLoader([os.path.join(args.sourcepath, 'templates/'), ]))
    env.filters.update(global_filters)

    # If there is a context json, load it as well
    context = load_context(source.readfile('templates/context.json'))

    # Fetch the current git revision if this is coming out of a git repository
    context['githash'] = git_revision

    # Load contexts in override directory, if any
    if source.isdir('templates/context.override.d'):
        for f in sorted(source.listfiles('templates/context.override.d')):
            if f.endswith('.json'):
                deep_update_context(context, load_context(source.readfile(os.path.join('templates/context.override.d', f))))

    knownfiles = []
    knownfiles = _deploy_static(source, args.destpath)

    # If we have a .deploystaticmap, parse that one instead of the full list of
    # parsing everything.
    fmap = source.readfile('templates/pages/.deploystaticmap')
    if fmap:
        for l in fmap.splitlines():
            (src, dest) = l.decode('utf8').split(':')
            if not os.path.isdir(os.path.join(args.destpath, dest)):
                os.makedirs(os.path.join(args.destpath, dest))
            context['page'] = dest
            deploy_template(env, os.path.join('pages', src),
                            os.path.join(args.destpath, dest, 'index.html'),
                            context)
            knownfiles.append(os.path.join(dest, 'index.html'))
    else:
        for relpath, fn in source.walkfiles('templates/pages'):
            # We only process HTML files in templates
            if os.path.splitext(fn)[1] != '.html':
                continue

            if fn == 'index.html':
                if relpath != 'templates/pages':
                    print("index.html can only be used in the root directory!")
                    sys.exit(1)
                destdir = ''
            else:
                noext = os.path.splitext(fn)[0]
                if relpath == 'templates/pages':
                    destdir = noext
                else:
                    destdir = '{0}/{1}'.format(relpath[len('templates/pages/'):], noext)

            if not os.path.isdir(os.path.join(args.destpath, destdir)):
                os.makedirs(os.path.join(args.destpath, destdir))

            context['page'] = destdir

            deploy_template(env, os.path.join(relpath[len('templates/'):], fn),
                            os.path.join(args.destpath, destdir, 'index.html'),
                            context)

            knownfiles.append(os.path.join(destdir, 'index.html'))

    remove_unknown(knownfiles, args.destpath)
