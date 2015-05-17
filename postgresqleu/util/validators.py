from django.core.exceptions import ValidationError

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
