from django.db import connection

import os
import shutil


_query_unique_constraints = """
SELECT c.relname, con.conname, array_agg(a.attname ORDER BY i) AS keys
FROM pg_constraint con
INNER JOIN pg_class c ON c.oid=con.conrelid
JOIN LATERAL UNNEST(con.conkey) WITH ordinality t(t, i) ON true
INNER JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=t.t
WHERE contype='u'
GROUP BY c.relname, con.conname
"""

_query_foreign_constraints = """
SELECT c.relname AS relname,
       fc.relname AS frelname,
       (SELECT attname FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum=con.conkey[1]) AS attname,
       (SELECT attname FROM pg_attribute fa WHERE fa.attrelid=fc.oid AND fa.attnum=con.confkey[1]) AS fattname,
       con.conname
FROM pg_constraint con
INNER JOIN pg_class c ON c.oid=con.conrelid
INNER JOIN pg_class fc ON fc.oid=con.confrelid
WHERE contype='f' AND array_length(conkey, 1) = 1
"""

_querymap = (
    ('expected_unique_constraints.csv', _query_unique_constraints, 'relname, conname'),
    ('expected_foreign_constraints.csv', _query_foreign_constraints, 'relname, attname'),
)


def dump_expected_files(directory):
    curs = connection.cursor()

    for fn, q, order in _querymap:
        with open(os.path.join(directory, fn), 'w') as f:
            curs.copy_expert("COPY ({} ORDER BY {}) TO STDOUT".format(q, order), f)


def scan_constraint_differences(directory, fix=False):
    curs = connection.cursor()

    def _print_cant_fix(msg):
        if fix:
            print("CAN'T FIX: {}".format(msg))
        else:
            print(msg)

    # Start with unique constraints
    with open(os.path.join(directory, 'expected_unique_constraints.csv')) as f:
        curs.execute("CREATE TEMPORARY TABLE _sync_unique_constraints_expected(relname text NOT NULL, conname text NOT NULL, keys name[] NOT NULL)")
        curs.copy_from(f, '_sync_unique_constraints_expected')

    curs.execute("WITH t AS ({}) SELECT e.relname, t.conname, e.conname FROM _sync_unique_constraints_expected e INNER JOIN t ON t.relname=e.relname AND t.keys=e.keys WHERE t.conname != e.conname".format(_query_unique_constraints))
    for relname, current, expected in curs.fetchall():
        if fix:
            print("Renaming unique constraint {} to {}".format(current, expected))
            curs.execute('ALTER TABLE "{}" RENAME CONSTRAINT "{}" TO "{}"'.format(relname, current, expected))
        else:
            print("Expected unique constraint {} to be named {}".format(current, expected))

    curs.execute("WITH t AS ({}) SELECT conname FROM t WHERE NOT EXISTS (SELECT 1 FROM _sync_unique_constraints_expected e WHERE e.relname=t.relname AND e.keys=t.keys)".format(_query_unique_constraints))
    for expected, in curs.fetchall():
        _print_cant_fix("Unique constraint {} should not exist".format(expected))

    curs.execute("WITH t AS ({}) SELECT conname FROM _sync_unique_constraints_expected e WHERE NOT EXISTS (SELECT 1 FROM t WHERE e.relname=t.relname AND e.keys=t.keys)".format(_query_unique_constraints))
    for current, in curs.fetchall():
        _print_cant_fix("Unique constraint {} is missing".format(current))

    # Then do foreign key ones
    with open(os.path.join(directory, 'expected_foreign_constraints.csv')) as f:
        curs.execute("CREATE TEMPORARY TABLE _sync_constraints_expected(relname text NOT NULL, frelname text NOT NULL, attname text NOT NULL, fattname text NOT NULL, conname text);")
        curs.copy_from(f, '_sync_constraints_expected')

    curs.execute("WITH t AS ({}) SELECT e.relname, t.conname, e.conname FROM _sync_constraints_expected e INNER JOIN t ON e.relname=t.relname AND e.frelname=t.frelname and e.attname=t.attname AND e.fattname=t.fattname WHERE t.conname != e.conname".format(_query_foreign_constraints))
    for relname, current, expected in curs.fetchall():
        if fix:
            print("Renaming foreign key constraint {} to {}".format(current, expected))
            curs.execute('ALTER TABLE "{}" RENAME CONSTRAINT "{}" TO "{}"'.format(relname, current, expected))
        else:
            _print_cant_fix("Expected foreign key constraint {} to be named {}".format(current, expected))

    curs.execute("WITH t AS ({}) SELECT conname FROM t WHERE NOT EXISTS (SELECT 1 FROM _sync_constraints_expected e WHERE e.relname=t.relname AND e.frelname=t.frelname and e.attname=t.attname AND e.fattname=t.fattname)".format(_query_foreign_constraints))
    for expected, in curs.fetchall():
        _print_cant_fix("Foreign key constraint {} should not exist".format(expected))

    curs.execute("WITH t AS ({}) SELECT conname FROM _sync_constraints_expected e WHERE NOT EXISTS (SELECT 1 FROM t WHERE e.relname=t.relname AND e.frelname=t.frelname and e.attname=t.attname AND e.fattname=t.fattname)".format(_query_foreign_constraints))
    for current, in curs.fetchall():
        _print_cant_fix("Foreign key constraint {} is missing".format(current))
