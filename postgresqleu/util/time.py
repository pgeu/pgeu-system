from django.utils import timezone


def today_conference():
    return timezone.now().date()


def today_global():
    return timezone.now().date()
