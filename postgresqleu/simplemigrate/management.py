from django.db.models import signals
from django.db import connection, transaction

import os
from glob import glob
import re

def process_sql_scripts(app, created_models, verbosity=2, **kwargs):
	if not app.__name__.startswith('postgresqleu.'): return

	namepieces = app.__name__.split('.')
	if len(namepieces) != 3: return
	if namepieces[2] != 'models': return
	appname = namepieces[1]

	if not os.path.isdir('%s/sqlupdate' % appname): return

	with transaction.commit_on_success():
		curs = connection.cursor()
		curs.execute("SELECT ver FROM _appscripts WHERE app=%s", [appname,])
		rows = curs.fetchall()
		if len(rows) == 0:
			# App not inserted yet, so do that
			curs.execute("INSERT INTO _appscripts (app,ver) VALUES (%s,%s)", [appname, 0])
			ver = 0
		else:
			ver = rows[0][0]

		for fn in sorted(glob('%s/sqlupdate/*.sql' % appname)):
			m = re.search('/(\d+)(-[^/]+)?\.sql$', fn)
			if not m: continue
			filever = int(m.groups(1)[0])
			if ver >= filever:
				print "SQL script %s already applied." % fn
				continue

			print "Applying SQL script %s" % fn
			with open(fn) as f:
				sql = f.read()
				curs.execute(sql)
				curs.execute("UPDATE _appscripts SET ver=%s WHERE app=%s", [filever, appname])

signals.post_syncdb.connect(process_sql_scripts)
