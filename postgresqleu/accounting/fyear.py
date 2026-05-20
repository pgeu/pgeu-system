"""
Financial Year Utilities

This module provides all functions needed to work with configurable
financial year boundaries. The financial year number is the calendar
year in which the financial year STARTS.

Example for UK (April 6 - April 5):
- Financial year 2024 runs from April 6, 2024 to April 5, 2025
- A date of March 1, 2024 belongs to financial year 2023
- A date of April 10, 2024 belongs to financial year 2024
"""
from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _parse_fy_start_month_day():
    """
    Parse and validate FIRST_DAY_OF_FINANCIAL_YEAR. Runs once at import so
    misconfiguration raises immediately instead of from inside a webhook
    handler later.
    """
    fy_start = getattr(settings, 'FIRST_DAY_OF_FINANCIAL_YEAR', '01-01')
    parts = fy_start.split('-')
    if len(parts) != 2:
        raise ImproperlyConfigured(
            "FIRST_DAY_OF_FINANCIAL_YEAR must be in 'MM-DD' format, got '{}'".format(fy_start)
        )
    try:
        month = int(parts[0])
        day = int(parts[1])
    except ValueError:
        raise ImproperlyConfigured(
            "FIRST_DAY_OF_FINANCIAL_YEAR must be in 'MM-DD' format with integer month and day, got '{}'".format(fy_start)
        )
    # Validate by constructing a date in a non-leap year (rejects Feb 29, which would
    # be ambiguous as a financial-year boundary).
    try:
        date(2001, month, day)
    except ValueError as e:
        raise ImproperlyConfigured(
            "FIRST_DAY_OF_FINANCIAL_YEAR '{}' is not a valid date: {}".format(fy_start, e)
        )
    return (month, day)


_FY_START_MONTH, _FY_START_DAY = _parse_fy_start_month_day()


def fy_start_date(year_number):
    """
    Get the start date for a financial year.

    Args:
        year_number: Integer financial year (e.g., 2024)

    Returns:
        date: First day of the financial year
    """
    return date(year_number, _FY_START_MONTH, _FY_START_DAY)


def fy_end_date(year_number):
    """
    Get the end date for a financial year.

    Args:
        year_number: Integer financial year (e.g., 2024)

    Returns:
        date: Last day of the financial year
    """
    # End date is day before start of next year
    next_start = date(year_number + 1, _FY_START_MONTH, _FY_START_DAY)
    return next_start - timedelta(days=1)


def date_to_fy(d):
    """
    Determine which financial year a date belongs to.

    Args:
        d: A date object

    Returns:
        int: The financial year number
    """
    fy_start_this_year = date(d.year, _FY_START_MONTH, _FY_START_DAY)

    if d >= fy_start_this_year:
        return d.year
    else:
        return d.year - 1


def format_fy_label(year_number):
    """
    Format year label for display.

    For calendar years (Jan 1 - Dec 31): returns "2024"
    For split years (e.g., UK April 6 - April 5): returns "2024/25"

    Args:
        year_number: Integer financial year

    Returns:
        str: Formatted year label
    """
    end = fy_end_date(year_number)
    if end.year != year_number:
        # Financial year spans two calendar years
        return "{}/{}".format(year_number, str(end.year)[-2:])
    else:
        return str(year_number)
