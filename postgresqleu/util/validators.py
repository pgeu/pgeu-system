from django.core.exceptions import ValidationError

def validate_lowercase(value):
	if value != value.lower():
		raise ValidationError("This field must be lowercase only")
