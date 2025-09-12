from django.db import connection

from postgresqleu.util.db import exec_to_scalar

import json


class InlineEncodedStorage(object):
    def __init__(self, key):
        self.key = key

    def read(self, name):
        curs = connection.cursor()
        curs.execute("SELECT encode(hashval, 'hex'), data, metadata FROM util_storage WHERE key=%(key)s AND storageid=%(id)s", {
            'key': self.key, 'id': name})
        rows = curs.fetchall()
        if len(rows) != 1:
            return None, None, None
        return rows[0][0], bytes(rows[0][1]), json.loads(rows[0][2])

    def get_metadata(self, name):
        curs = connection.cursor()
        curs.execute("SELECT metadata FROM util_storage WHERE key=%(key)s AND storageid=%(id)s", {
            'key': self.key, 'id': name})
        rows = curs.fetchall()
        if len(rows) != 1:
            return None, None
        return json.loads(rows[0][0])

    def save(self, name, content, metadata=None):
        content.seek(0)
        curs = connection.cursor()
        params = {
            'key': self.key,
            'id': name,
            'data': content.read(),
            'metadata': json.dumps(metadata if metadata else {}),
            }
        curs.execute("UPDATE util_storage SET data=%(data)s, metadata=%(metadata)s WHERE key=%(key)s AND storageid=%(id)s", params)
        if curs.rowcount == 0:
            curs.execute("INSERT INTO util_storage (key, storageid, data, metadata) VALUES (%(key)s, %(id)s, %(data)s, %(metadata)s)", params)
        return name

    def get_tag(self, name):
        return exec_to_scalar("SELECT encode(hashval, 'hex') FROM util_storage WHERE key=%(key)s AND storageid=%(id)s", {
            'key': self.key,
            'id': name,
        })

    def delete(self, name):
        curs = connection.cursor()
        curs.execute("DELETE FROM util_storage WHERE key=%(key)s AND storageid=%(id)s", {
            'key': self.key,
            'id': name,
        })


def inlineencoded_upload_path(instance, filename):
    # Needs to exist for old migrations, but *NOT* in use
    return None
