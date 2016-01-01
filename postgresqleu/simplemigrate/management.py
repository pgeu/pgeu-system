from django.db.models import signals
from django.db import connection, transaction

import os
from glob import glob
import re

def _get_app_files(appname):
	for fn in sorted(glob('%s/sqlupdate/*.sql' % appname)):
		m = re.search('/(\d+)(-[^/]+)?\.sql$', fn)
		if not m: continue
		yield (fn, int(m.groups(1)[0]))

def process_sql_scripts(app, created_models, verbosity=2, **kwargs):
	if not app.__name__.startswith('postgresqleu.'): return

	namepieces = app.__name__.split('.')
	if len(namepieces) != 3: return
	if namepieces[2] != 'models': return
	appname = namepieces[1]

	with transaction.atomic():
		appfiles = list(_get_app_files(appname))
		curs = connection.cursor()
		curs.execute("SELECT ver FROM _appscripts WHERE app=%s", [appname,])
		rows = curs.fetchall()
		if len(rows) == 0:
			# App not inserted yet, so do that
			if len(appfiles):
				# One or more appfiles exist, so we need to bypass them. This is the normal
				# usecase when doing a completely new deployment.
				(lastfile, lastver) = appfiles[-1]
				print "Initializing SQL update scripts for %s, setting last version to %s" % (appname, lastver)
				curs.execute("INSERT INTO _appscripts (app,ver) VALUES (%s,%s)", [appname, lastver])
				ver = lastver
			else:
				# No appfiles exist, meaning that this model has no updates. We do, however,
				# insert an empty record for it specifically so that we can handle the *next* time an
				# update shows up. Once the file shows up it will then be applied, whereas a completely
				# new deployment will have nothing and still bypass it.
				print "Initializing empty SQL update scripts for %s" % appname
				curs.execute("INSERT INTO _appscripts (app,ver) VALUES (%s,%s)", [appname, 0])
				ver = 0
		else:
			ver = rows[0][0]

		for (fn, filever) in appfiles:
			if ver >= filever:
				print "SQL script %s already applied." % fn
				continue

			print "Applying SQL script %s" % fn
			with open(fn) as f:
				sql = f.read()
				curs.execute(sql)
				curs.execute("UPDATE _appscripts SET ver=%s WHERE app=%s", [filever, appname])

signals.post_syncdb.connect(process_sql_scripts)
