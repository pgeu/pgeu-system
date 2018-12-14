from django.db import connection
import collections

def exec_no_result(query, params=None):
    curs = connection.cursor()
    curs.execute(query, params)

def exec_to_list(query, params=None):
    curs = connection.cursor()
    curs.execute(query, params)
    return curs.fetchall()

def exec_to_dict(query, params=None):
    curs = connection.cursor()
    curs.execute(query, params)
    columns = [col[0] for col in curs.description]
    return [dict(zip(columns, row))for row in curs.fetchall()]

def exec_to_scalar(query, params=None):
    curs = connection.cursor()
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
    curs = connection.cursor()
    curs.execute(query, params)
    columns = [col[0] for col in curs.description]
    return {r[columns[0]]:r for r in (dict(zip(columns, row))for row in curs.fetchall())}

def exec_to_grouped_dict(query, params=None):
    curs = connection.cursor()
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
        curr.append(dict(zip(columns, row[1:])))
    if last:
        full[last] = curr
    return full
