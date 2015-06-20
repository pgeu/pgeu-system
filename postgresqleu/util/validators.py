from django.core.exceptions import ValidationError

import httplib
import socket

def validate_lowercase(value):
	if value != value.lower():
		raise ValidationError("This field must be lowercase only")


class BeforeValidator(object):
	def __init__(self, beforedate):
		self.beforedate = beforedate

	def __call__(self, value):
		if value >= self.beforedate:
			raise ValidationError("Ensure this date is before {0}".format(self.beforedate))

class AfterValidator(object):
	def __init__(self, afterdate):
		self.afterdate = afterdate

	def __call__(self, value):
		if value <= self.afterdate:
			raise ValidationError("Ensure this date is after {0}".format(self.afterdate))


def TwitterValidator(value):
	if value.startswith('@'):
		value = value[1:]

	conn = httplib.HTTPSConnection("twitter.com", timeout=5, strict=True)
	conn.request('HEAD', '/{0}'.format(value))
	conn.sock.settimeout(5) # 5 second TCP timeout
	try:
		r = conn.getresponse()
	except socket.timeout:
		raise ValidationError("Could not verify twitter name - timeout")
	if r.status != 200:
		raise ValidationError("Could not verify twitter name: {0}".format(r.status))

	# All is well! :)
