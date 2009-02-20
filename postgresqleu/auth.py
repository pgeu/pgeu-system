from django.contrib.auth.models import User
from django.contrib.auth.backends import ModelBackend
from django.conf import settings
import psycopg2

class AuthBackend(ModelBackend):
	def authenticate(self, username=None, password=None):
		conn = psycopg2.connect(settings.AUTH_CONNECTION_STRING)
		try:
			conn.set_client_encoding('UNICODE')
			cur = conn.cursor()
			cur.execute('SELECT * FROM community_login(%s,%s)', (username, password))
			row  = cur.fetchall()[0]
		finally:
			conn.close()

		if row[1] == 1:
			try:
				user = User.objects.get(username=username)
			except User.DoesNotExist:
				# User doesn't exist yet
				user = User(username=username, password='setmanually', email=row[3], first_name=row[2])
				user.save()
			return user
		return None

	def get_user(self, user_id):
		try:
			return User.objects.get(pk=user_id)
		except User.DoesNotExist:
			return None
