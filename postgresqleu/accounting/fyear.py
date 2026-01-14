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


def get_fy_start_month_day():
    """
    Parse FIRST_DAY_OF_FINANCIAL_YEAR setting.

    Returns:
        tuple: (month, day) as integers
    """
    fy_start = getattr(settings, 'FIRST_DAY_OF_FINANCIAL_YEAR', '01-01')
    parts = fy_start.split('-')
    return (int(parts[0]), int(parts[1]))


def fy_start_date(year_number):
    """
    Get the start date for a financial year.

    Args:
        year_number: Integer financial year (e.g., 2024)

    Returns:
        date: First day of the financial year
    """
    month, day = get_fy_start_month_day()
    return date(year_number, month, day)


def fy_end_date(year_number):
    """
    Get the end date for a financial year.

    Args:
        year_number: Integer financial year (e.g., 2024)

    Returns:
        date: Last day of the financial year
    """
    month, day = get_fy_start_month_day()
    # End date is day before start of next year
    next_start = date(year_number + 1, month, day)
    return next_start - timedelta(days=1)


def date_to_fy(d):
    """
    Determine which financial year a date belongs to.

    Args:
        d: A date object

    Returns:
        int: The financial year number
    """
    month, day = get_fy_start_month_day()
    fy_start_this_year = date(d.year, month, day)

    if d >= fy_start_this_year:
        return d.year
    else:
        return d.year - 1


def fy_date_range_display(year_number):
    """
    Get a formatted string showing the financial year date range.

    Args:
        year_number: Integer financial year

    Returns:
        str: e.g., "2024-04-06 - 2025-04-05" or "2024-01-01 - 2024-12-31"
    """
    start = fy_start_date(year_number)
    end = fy_end_date(year_number)
    return "{} - {}".format(start, end)


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


def is_calendar_year():
    """
    Check if the system is using calendar year accounting.

    Returns:
        bool: True if using calendar year (Jan 1 - Dec 31)
    """
    month, day = get_fy_start_month_day()
    return month == 1 and day == 1
