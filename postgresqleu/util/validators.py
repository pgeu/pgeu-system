from django.core.exceptions import ValidationError

import requests

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

	if value == '':
		# This can only happen if it was '@' initially
		raise ValidationError("Enter twitter name or leave field empty")

	try:
		r = requests.head('https://twitter.com/{0}'.format(value),
						  headers={'User-agent': 'Firefox/60'},
						  timeout=5)
	except requests.exceptions.ReadTimeout:
		raise ValidationError("Could not verify twitter name - timeout")

	if r.status_code != 200:
		raise ValidationError("Could not verify twitter name: {0}".format(r.status_code))

	# All is well! :)
