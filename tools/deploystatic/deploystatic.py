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
import re
import unicodedata
import io
import subprocess
import tarfile

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
	return sorted(group, key=lambda y: y[0] and getattr(y[0], sortkey) or None)

# Shuffle the order in a list, for example to randomize the order of sponsors
def filter_shuffle(l):
	try:
		r = list(l)
		random.shuffle(r)
		return r
	except:
		return l

# Format a datetime. If it'sa datetime, call strftime. If it's a
# string, assume it's iso format and convert it to a date first.
def filter_datetimeformat(value, fmt):
	if isinstance(value, date) or isinstance(value, datetime) or isinstance(value,time):
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
		return os.listdir(os.path.join(self.root, d))

	def copy_if_changed(self, relsource, fulldest):
		fullsrc = os.path.join(self.root, relsource)
		if (not os.path.exists(fulldest)) or (not filecmp.cmp(fullsrc, fulldest)):
			shutil.copy2(fullsrc, fulldest)

	def readfile(self, src):
		if os.path.isfile(os.path.join(self.root, src)):
			with open(os.path.join(self.root, src)) as f:
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
		return self.tarstruct.has_key(d) and self.tarstruct[d].isdir()

	def isfile(self, f):
		return self.tarstruct.has_key(f) and self.tarstruct[f].isfile()

	def readfile(self, src):
		if self.tarstruct.has_key(src) and self.tarstruct[src].isfile():
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
			with open(fulldest, 'r') as f:
				x = f.read()
				if x == sourcedata:
					return

		with open(fulldest, 'w') as f:
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
		return json.loads(jsondata)
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
	parser.add_argument('--branch', type=str, help='Deploy directly from branch')

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

	if args.branch:
		s = subprocess.Popen(['/usr/bin/git', 'archive', '--format=tar', args.branch],
							 stdout=subprocess.PIPE,
							 cwd=args.sourcepath)
		source = TarWrapper(s.stdout)
		s.stdout.close()
	else:
		source = SourceWrapper(args.sourcepath)

	for d in ('templates', 'templates/pages', 'static'):
		if not source.isdir(d):
			print "'{0}' subdirectory does not exist in source!".format(d)
			sys.exit(1)

	staticdest = os.path.join(args.destpath, 'static/')

	# Set up jinja environment
	if args.branch:
		env = jinja2.sandbox.SandboxedEnvironment(loader=JinjaTarLoader(source))
	else:
		env = jinja2.sandbox.SandboxedEnvironment(loader=jinja2.FileSystemLoader([os.path.join(args.sourcepath, 'templates/'),]))
	env.filters.update(global_filters)

	# If there is a context json, load it as well
	context = load_context(source.readfile('templates/context.json'))

	# Fetch the current git revision if this is coming out of a git repository
	context['githash'] = find_git_revision(args.sourcepath)

	# Load a context that can override everything, including static hashes
	context.update(load_context(source.readfile('templates/context.override.json')))


	knownfiles = []
	# We could use copytree(), but we need to know which files are there so we can
	# remove old files, so we might as well do the full processing this way.
	for relpath, relname in source.walkfiles('static'):
		if not os.path.isdir(os.path.join(args.destpath, relpath)):
			os.makedirs(os.path.join(args.destpath, relpath))

		relsource = os.path.join(relpath, relname)
		source.copy_if_changed(relsource, os.path.join(args.destpath, relsource))

		knownfiles.append(relsource)

	for fn in source.listfiles('templates/pages'):
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
