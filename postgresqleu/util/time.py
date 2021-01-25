from django.utils import timezone
from django.utils.timesince import timeuntil, timesince
from django.utils.formats import date_format


# Return a date represeting today in the timezone of the currently
# selected conference. If no conference is selected, the date will
# be returned in the global default timezone.
def today_conference():
    return timezone.localdate(timezone.now())


# Return a date represeting today ihn the global default timezone
# (making it suitable for everything that is not conference-related).
def today_global():
    return timezone.localdate(timezone.now(), timezone.get_default_timezone())


# Return a string representing time until or time since, depending
def time_sinceoruntil(t):
    if t >= timezone.now():
        return "in {}".format(timeuntil(t))
    else:
        return "{} ago".format(timesince(t))


# Format a datetime long string
def datetime_string(t):
    return date_format(timezone.localtime(t), 'DATETIME_FORMAT', use_l10n=False)
