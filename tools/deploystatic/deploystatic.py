#!/usr/bin/env python
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

import jinja2
import jinja2.sandbox

#
# Some useful filters. We include them inline in this file to make it
# standalone useful.
#
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

global_filters = {
	'groupby_sort': filter_groupby_sort,
	'shuffle': filter_shuffle,
}


# Optionally load a JSON context
def load_context(jsonfile):
	if os.path.isfile(jsonfile):
		with open(jsonfile) as f:
			return json.load(f)
	else:
		return {}

# Locate which git revision we're on
def find_git_revision(path):
	while path != '/':
		if os.path.exists(os.path.join(path, ".git/HEAD")):
			# Found it!
			with open(os.path.join(path, '.git/HEAD')) as f:
				ref = f.readline().strip()
			if not ref.startswith('ref: refs/heads/'):
				print "Invalid git reference {0}".format(ref)
				return None
			refname = os.path.join(path, ".git/", ref[5:])
			if not os.path.isfile(refname):
				print "Could not find git ref {0}".format(refname)
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
	s = t.render(**context).encode('utf8')

	# Only write the file if it has actually changed
	if os.path.isfile(destfile):
		with open(destfile) as f:
			if f.read() == s:
				return

	with open(destfile, 'w') as f:
		f.write(s)


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Deploy jinja based static site')
	parser.add_argument('sourcepath', type=str, help='Source path')
	parser.add_argument('destpath', type=str, help='Destination path')

	args = parser.parse_args()

	if not os.path.isabs(args.sourcepath):
		print "Source path is not absolute!"
		sys.exit(1)
	if not os.path.isabs(args.destpath):
		print "Destination path is not absolute!"
		sys.exit(1)

	if not os.path.isdir(args.sourcepath):
		print "Source directory does not exist!"
		sys.exit(1)

	if not os.path.isdir(args.destpath):
		print "Destination directory does not exist!"
		sys.exit(1)

	for d in ('templates', 'templates/pages', 'static'):
		if not os.path.isdir(os.path.join(args.sourcepath, d)):
			print "'{0}' subdirectory does not exist in source!".format(d)
			sys.exit(1)

	staticroot = os.path.join(args.sourcepath, 'static/')
	staticdest = os.path.join(args.destpath, 'static/')

	# Set up jinja environment
	env = jinja2.sandbox.SandboxedEnvironment(loader=jinja2.FileSystemLoader([os.path.join(args.sourcepath, 'templates/'),]))
	env.filters.update(global_filters)

	# If there is a context json, load it as well
	context = load_context(os.path.join(args.sourcepath, 'templates', 'context.json'))

	# Fetch the current git revision if this is coming out of a git repository
	context['githash'] = find_git_revision(args.sourcepath)

	# Load a context that can override everything, including static hashes
	context.update(load_context(os.path.join(args.sourcepath, 'templates', 'context.override.json')))


	knownfiles = []
	# We could use copytree(), but we need to know which files are there so we can
	# remove old files, so we might as well do the full processing this way.
	for dn, subdirs, filenames in os.walk(staticroot):
		relpath = os.path.relpath(dn, staticroot)
		if not os.path.isdir(os.path.join(staticdest, relpath)):
			os.makedirs(os.path.join(staticdest, relpath))

		for fn in filenames:
			fullsrc = os.path.join(staticroot, relpath, fn)
			fulldest = os.path.join(staticdest, relpath, fn)
			if (not os.path.exists(fulldest)) or (not filecmp.cmp(fullsrc, fulldest)):
				shutil.copy2(fullsrc, fulldest)
			knownfiles.append(os.path.join('static', relpath, fn))

	pagesroot = os.path.join(args.sourcepath, 'templates/pages')
	for fn in os.listdir(pagesroot):
		# We don't use subdirectories yet, so don't bother even looking at that
		if os.path.splitext(fn)[1] != '.html':
			continue

		if fn == 'index.html':
			destdir = ''
		else:
			destdir = os.path.splitext(fn)[0]

		if not os.path.isdir(os.path.join(args.destpath, destdir)):
			os.mkdir(os.path.join(args.destpath, destdir))

		context['page'] = destdir

		deploy_template(env, os.path.join('pages', fn),
						os.path.join(args.destpath, destdir, 'index.html'),
						context)

		knownfiles.append(os.path.join(destdir, 'index.html'))

	# Look for things to remove
	for dn, subdirs, filenames in os.walk(args.destpath):
		relpath = os.path.relpath(dn, args.destpath)
		if relpath == '.':
			relpath = ''
		for fn in filenames:
			f = os.path.join(relpath, fn)
			if not f in knownfiles:
				os.unlink(os.path.join(args.destpath, f))
