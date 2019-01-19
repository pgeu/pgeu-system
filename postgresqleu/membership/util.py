from django.core.exceptions import ValidationError

country_validator_choices = [
    ('europe', 'Must be from European country'),
]


def validate_country(validator, country):
    if not validator:
        return

    if validator == 'europe':
        if not hasattr(country, 'europecountry'):
            raise ValidationError("Membership is available to people living in geographical Europe.")
        return

    raise ValidationError("Invalid validator '{}' configured".format(validator))
