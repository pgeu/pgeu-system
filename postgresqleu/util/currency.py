from django.conf import settings


# Format a currency value for proper display
def format_currency(value):
    return settings.CURRENCY_FORMAT.format(
        SYMBOL=settings.CURRENCY_SYMBOL,
        ABBREV=settings.CURRENCY_ABBREV,
        AMOUNT='{:.2f}'.format(value))
