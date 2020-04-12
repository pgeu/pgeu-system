from django.utils import timezone


# Return a date represeting today in the timezone of the currently
# selected conference. If no conference is selected, the date will
# be returned in the global default timezone.
def today_conference():
    return timezone.localdate(timezone.now())


# Return a date represeting today ihn the global default timezone
# (making it suitable for everything that is not conference-related).
def today_global():
    return timezone.localdate(timezone.now(), timezone.get_default_timezone())
