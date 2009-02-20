from django.contrib.auth.models import User
import psycopg2

class AuthBackend:
	def authenticate(self, username=None, password=None):
		conn = psycopg2.connect('host=wwwmaster.postgresql.org dbname=186_www user=auth_svc password=g7y3m9u8 sslmode=require')
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
