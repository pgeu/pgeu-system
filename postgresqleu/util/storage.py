import base64
import cStringIO as StringIO
from django.core.files.storage import Storage
from django.core.files import File
from django.db import connection
from django.db.models import FileField
from django.utils.deconstruct import deconstructible

@deconstructible
class InlineEncodedStorage(Storage):
	def __init__(self, key):
		self.key = key

	def _open(self, name, mode='rb'):
		curs = connection.cursor()
		curs.execute("SELECT data FROM util_storage WHERE key=%(key)s AND storageid=%(id)s", {
			'key': self.key, 'id': name})
		rows = curs.fetchall()
		if len(rows) != 1:
			return None
		return File(StringIO.StringIO(base64.b64decode(rows[0][0])))

	def _save(self, name, content):
		content.seek(0)
		curs = connection.cursor()
		params = {
			'key': self.key,
			'id': name,
			'data': base64.b64encode(content.read()),
			}
		curs.execute("UPDATE util_storage SET data=%(data)s WHERE key=%(key)s AND storageid=%(id)s", params)
		if curs.rowcount == 0:
			curs.execute("INSERT INTO util_storage (key, storageid, data) VALUES (%(key)s, %(id)s, %(data)s)", params)
		return name

	def exists(self, name):
		return False # Not sure why, but we don't need it :)

	def get_available_name(self, name):
		return name

	def _delete(self, name):
		curs = connection.cursor()
		curs.execute("DELETE FROM util_storage WHERE key=%(key)s AND storageid=%(id)s",
					 {'key': self.key, 'id': name})

	def url(self, name):
		# XXX: THIS NEEDS TO BE A PARAMETER TO THE CLASS!
		return "/events/sponsorship/contracts/%s/" % name

	def size(self, name):
		return None

	def path(self):
		return None

def inlineencoded_upload_path(instance, filename):
	return "%s" % instance.id

def delete_inline_storage(sender, **kwargs):
	kwargs['instance'].delete_inline_storage()
