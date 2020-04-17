from django.db import connection
from django.conf import settings
import collections

from psycopg2.tz import LocalTimezone


def get_native_cursor():
    # Remove djangos dumb prevention of us to change the timezone
    curs = connection.cursor()
    curs.cursor.tzinfo_factory = LocalTimezone
    return curs


def exec_no_result(query, params=None):
    curs = get_native_cursor()
    curs.execute(query, params)


def exec_to_list(query, params=None):
    curs = get_native_cursor()
    curs.execute(query, params)
    return curs.fetchall()


def exec_to_single_list(query, params=None):
    curs = get_native_cursor()
    curs.execute(query, params)
    return [r[0] for r in curs.fetchall()]


def exec_to_dict(query, params=None):
    curs = get_native_cursor()
    curs.execute(query, params)
    columns = [col[0] for col in curs.description]
    return [dict(list(zip(columns, row)))for row in curs.fetchall()]


def exec_to_scalar(query, params=None):
    curs = get_native_cursor()
    curs.execute(query, params)
    r = curs.fetchone()
    if r:
        return r[0]
    # If the query returns no rows at all, then just return None
    return None


def conditional_exec_to_scalar(condition, query, params=None):
    if condition:
        return exec_to_scalar(query, params)
    else:
        return False


def exec_to_keyed_dict(query, params=None):
    curs = get_native_cursor()
    curs.execute(query, params)
    columns = [col[0] for col in curs.description]
    return {r[columns[0]]: r for r in (dict(list(zip(columns, row)))for row in curs.fetchall())}


def exec_to_keyed_scalar(query, params=None):
    curs = get_native_cursor()
    curs.execute(query, params)
    return dict(curs.fetchall())


def exec_to_grouped_dict(query, params=None):
    curs = get_native_cursor()
    curs.execute(query, params)
    columns = [col[0] for col in curs.description[1:]]
    full = collections.OrderedDict()
    last = None
    curr = []
    for row in curs.fetchall():
        if last != row[0]:
            if curr:
                full[last] = curr
            curr = []
            last = row[0]
        curr.append(dict(list(zip(columns, row[1:]))))
    if last:
        full[last] = curr
    return full


class ensure_conference_timezone():
    """
    This context handler will set the timezone *in PostgreSQL* to the one from the
    specified conference, and reset it back to UTC when it's done. During this time,
    calls from django's own ORM will fail, it's intended only to wrap native SQL
    querying that needs to use the appropriate timezone.
    If None is specified as the conference, set the timezone to the global one for
    the installation (otherwise the default is UTC).
    """
    def __init__(self, conference):
        if conference is None:
            self.tzname = settings.TIME_ZONE
        else:
            self.tzname = conference.tzname

    def __enter__(self):
        c = get_native_cursor()
        c.execute("SET TIMEZONE=%(tz)s", {
            'tz': self.tzname,
        })
        return c

    def __exit__(self, *args):
        connection.cursor().execute("SET TIMEZONE='UTC'")
