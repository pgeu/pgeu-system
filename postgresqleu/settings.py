#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys

from django.conf import global_settings

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

# Django settings for postgresqleu project.

DEBUG = False
DEBUG_TOOLBAR = False
INTERNAL_IPS = [
    '127.0.0.1',
]

DEFAULT_EMAIL = 'webmaster@localhost'

ADMINS = (
    ('webmaster', DEFAULT_EMAIL),
)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'postgresqleu',
        'USER': 'postgresqleu',
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'Europe/Paris'

# Enable timezone handling
USE_TZ = True

# Language code for this installation. All choices can be found here:
# http://www.i18nguy.com/unicode/language-identifiers.html
LANGUAGE_CODE = 'en-us'

SITE_ID = 1

# If you set this to False, Django will make some optimizations so as not
# to load the internationalization machinery.
USE_I18N = False

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash if there is a path component (optional in other cases).
STATIC_URL = '/media/'
STATICFILES_DIRS = (
    'media/',
)

# Must always be overridden in local_settings!
SECRET_KEY = ''

MIDDLEWARE = [
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'postgresqleu.util.middleware.RedirectMiddleware',
    'postgresqleu.util.middleware.TzMiddleware',
]

CSRF_FAILURE_VIEW = 'postgresqleu.views.csrf_failure'

ROOT_URLCONF = 'postgresqleu.urls'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': ['template', ],
    'OPTIONS': {
        'context_processors': [
            'django.template.context_processors.request',
            'django.contrib.auth.context_processors.auth',
            'django.contrib.messages.context_processors.messages',
            'postgresqleu.util.context_processors.settings_context',
        ],
        'loaders': [
            'django.template.loaders.filesystem.Loader',
            'django.template.loaders.app_directories.Loader',
        ],
    },
}]

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'postgresqleu.util.apps.UtilAppConfig',  # Must be *before* admin
    'django.contrib.messages',
    'django.contrib.admin',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'postgresqleu.static',
    'postgresqleu.countries',
    'postgresqleu.scheduler.apps.SchedulerAppConfig',
    'postgresqleu.digisign',
    'postgresqleu.paypal',
    'postgresqleu.adyen',
    'postgresqleu.newsevents',
    'postgresqleu.confreg',
    'postgresqleu.confsponsor.apps.ConfsponsorAppConfig',
    'postgresqleu.confwiki',
    'postgresqleu.mailqueue',
    'postgresqleu.invoices',
    'postgresqleu.accounting',
    'postgresqleu.trustlypayment',
    'postgresqleu.braintreepayment',
    'postgresqleu.stripepayment',
    'postgresqleu.transferwise',
    'postgresqleu.plaid',
    'postgresqleu.membership',
    'postgresqleu.elections',
]

# Root directory for DejaVu truetype fonts
FONTROOT = "/usr/share/fonts/truetype/ttf-dejavu"

# Locations of static assets
ASSETS = {
    # Bootstrap 4 is used for the public default site, the default conference site,
    # and in the shipment system frontend
    "bootstrap4": {
        "css": {"https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/css/bootstrap.min.css": "sha384-Gn5384xqQ1aoWXA+058RXPxPg6fy4IWvTNh0E263XmFcJlSAwiGgFAW/dAiS6JXm"},
        "js": {"https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0/js/bootstrap.min.js": "sha384-JZR6Spejh4U02d8jOt6vLEHfe/JQGiRRSQQxSfFWpi1MquVdAyjUar5+76PVCmYl"},
    },

    # Bootstrap 3 is used in the backend
    "bootstrap3": {
        "css": "/media/css/bootstrap.min.css",
        "js": "/media/js/bootstrap.min.js",
    },

    # JQuery 1.9 is used in the backend and in the twitter and scanning frontends
    "jquery1": {
        "js": "/media/jq/jquery-1.9.1.min.js",
    },

    # JQuery 3 is used on the default main site
    "jquery3": {
        "js": {"https://code.jquery.com/jquery-3.2.1.slim.min.js": "sha384-KJ3o2DKtIkvYIK3UENzmM7KCkRr/rE9/Qpg6aAZGJwFDMVNA/GpGFF93hXpG5KkN"},
    },

    # JQuery-ui is used in admin overrides and conference reports
    "jqueryui1": {
        "css": "/media/jq/jquery-ui.min.css",
        "js": "/media/jq/jquery-ui.min.js",
    },

    "fontawesome4": {
        "css": "/media/css/font-awesome.css",
    },

    "fontawesome6": {
        "css": {"https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.0/css/all.min.css": "sha512-xh6O/CkQoPOWDdYTDqeRdPCVd1SpvCA9XXcUnZS2FmJNp1coAFzvtCN9BmamE+4aHK8yyUHUSCcJHgXloTyT2A=="},
    },

    "selectize": {
        "css": [
            "/media/css/selectize.css",
            "/media/css/selectize.default.css",
        ],
        "js": "/media/js/selectize.min.js",
    },
}

ASSETS_OVERRIDE = {}

# List of IP addresses (v4 and v6) that is allowed to access monitoring urls
MONITOR_SERVER_IPS = []

# Email address used to send emails from the invoice system, or other
# parts of the "finance" system.
INVOICE_SENDER_EMAIL = DEFAULT_EMAIL

# Email address that receives notifications from the invoice system, or
# other parts of the "finance" system.
# INVOICE_NOTIFICATION_RECEIVER = DEFAULT_EMAIL


# Currency parameter
CURRENCY_ABBREV = 'EUR'
CURRENCY_SYMBOL = '€'
CURRENCY_ISO = 'EUR'

# Define how currency amounts should be formatted.
# You can use SYMBOL and ABBREV to insert the respective values above.
# AMOUNT should always be included of course, and will be the value to
# two decimal places (cents/pennies/whatever).
# Other text (spaces etc.) may be included as required.
#
# Euro format is "EUR nnnn" ('{ABBREV} {AMOUNT}') in English, Maltese,
# and Irish text (should usually be the case until pgeu-system is localised).
#
# Other European languages should use  "nnnn EUR" ('{AMOUNT} {ABBREV}').
#
# Per: https://publications.europa.eu/code/en/en-370303.htm
#
# Pound Sterling (UK GBP) format is "£nnnn" ('{SYMBOL}{AMOUNT}').
#
# Per: https://www.imperial.ac.uk/brand-style-guide/writing/numbers/money-and-currencies/

CURRENCY_FORMAT = '{ABBREV} {AMOUNT}'

# Method used for bank payments (used only in descriptive texts)
BANK_TRANSFER_METHOD_NAME = 'IBAN'

# Process EU-specific VAT rules
EU_VAT = False
# Home country prefix for EU VAT
EU_VAT_HOME_COUNTRY = "FR"
# On-line validate EU vat numbers
EU_VAT_VALIDATE = False

# Invoice module
# --------------
INVOICE_PDF_BUILDER = 'postgresqleu.util.misc.baseinvoice.BaseInvoice'
REFUND_PDF_BUILDER = 'postgresqleu.util.misc.baseinvoice.BaseRefund'

# Account numbers used for auto-accounting
ENABLE_AUTO_ACCOUNTING = False
ACCOUNTING_MANUAL_INCOME_ACCOUNT = 1930
ACCOUNTING_CONFREG_ACCOUNT = 3003
ACCOUNTING_CONFSPONSOR_ACCOUNT = 3004
ACCOUNTING_MEMBERSHIP_ACCOUNT = 3001
ACCOUNTING_DONATIONS_ACCOUNT = 3601
ACCOUNTING_INVOICE_VAT_ACCOUNT = 2610


# Organisation configuration
# --------------------------
ORG_NAME = "Not Configured Organisation"
ORG_SHORTNAME = "NOTCONF"
# Base URLs for generating absolute URLs
SITEBASE = "http://localhost:8000"
# Set cookies to secure to explicitly force off in the local settings
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

DATETIME_FORMAT = "Y-m-d H:i:s"
DATE_FORMAT = "Y-m-d"
TIME_FORMAT = "H:i:s"

# Enable/disable modules
# ----------------------
ENABLE_PG_COMMUNITY_AUTH = False
ENABLE_OAUTH_AUTH = False
ENABLE_NEWS = True
ENABLE_MEMBERSHIP = False
ENABLE_ELECTIONS = False

# When using oauth login, define providers
OAUTH = {}

# Set to a username and password in local_settings.py to enable global http auth
GLOBAL_LOGIN_USER = ''
GLOBAL_LOGIN_PASSWORD = ''

# Email to send info about scheduled jobs to
SCHEDULED_JOBS_EMAIL = DEFAULT_EMAIL

# Email to send info about scheduled jobs from
# SCHEDULED_JOBS_EMAIL_SENDER = DEFAULT_EMAIL

# Treasurer email address. This is only used as pass-through to templates for
# end-user reference, and never actually by the system to send and receive.
TREASURER_EMAIL = DEFAULT_EMAIL

# List of directories to watch for changes for reloadable services. If none
# is specified, then the django autoreloader (which can be pretty high in
# performance overhead) is used.
RELOAD_WATCH_DIRECTORIES = []

# If using plaid, control which countries are enable when adding accounts
# (must match account cofig)
PLAID_COUNTRIES = ['US', 'CA']
# Plaid production level (sandbox, development or production)
PLAID_LEVEL = 'development'

# If using the web based meetings, base URL for the web sockets server that
# handles the messages.
# Typically something like wss://some.domain.org/ws/meeting
MEETINGS_WS_BASE_URL = None
# If using the web based meetings, base URL to retrieve the status for the
# meeting server. If it starts with /, a unix socket in that location will
# be used instead of TCP.
MEETINGS_STATUS_BASE_URL = None

# If there is a local_settings.py, let it override our settings
try:
    from .local_settings import *
except ImportError as e:
    pass

PRELOAD_URLS = []
if 'SYSTEM_SKIN_DIRECTORY' in globals():
    # A skin directory is configured!
    # First, add it to templates
    HAS_SKIN = True

    TEMPLATES[0]['DIRS'].insert(0, os.path.join(SYSTEM_SKIN_DIRECTORY, 'template/'))

    sys.path.insert(0, os.path.join(SYSTEM_SKIN_DIRECTORY, 'code/'))

    # Load a skin settings file (URLs etc)
    try:
        from skin_settings import *
    except ImportError as e:
        pass
    # Then, load a local settings file from there
    try:
        from skin_local_settings import *
    except ImportError as e:
        pass
    if 'SKIN_APPS' in globals():
        INSTALLED_APPS.extend(SKIN_APPS)
else:
    HAS_SKIN = False


if not SECRET_KEY:
    raise Exception("SECRET_KEY must be configured!")

# Reset admins based on config params from skins and local
ADMINS = (
    ('{0} webmaster'.format(ORG_NAME), DEFAULT_EMAIL),
)
MANAGERS = ADMINS


# Fonts setup if not already done
_dejavu_fonts = [
    ('DejaVu Serif', '{}/DejaVuSerif.ttf'.format(FONTROOT)),
    ('DejaVu Serif Italic', '{}/DejaVuSerif-Italic.ttf'.format(FONTROOT)),
    ('DejaVu Serif Bold', '{}/DejaVuSerif-Bold.ttf'.format(FONTROOT)),
]
if 'REGISTER_FONTS' not in locals():
    REGISTER_FONTS = _dejavu_fonts
else:
    REGISTER_FONTS = _dejavu_fonts + REGISTER_FONTS

# Invoice module
# --------------
INVOICE_TITLE_PREFIX = '{0} Invoice'.format(ORG_NAME)
INVOICE_FILENAME_PREFIX = ORG_SHORTNAME.lower()


if GLOBAL_LOGIN_USER:
    MIDDLEWARE.append('postgresqleu.util.middleware.GlobalLoginMiddleware')

if ENABLE_PG_COMMUNITY_AUTH:
    AUTHENTICATION_BACKENDS = (
        'postgresqleu.auth.AuthBackend',
    )
    LOGIN_URL = "{0}/accounts/login/".format(SITEBASE)

if ENABLE_ELECTIONS and not ENABLE_MEMBERSHIP:
    raise Exception("Elections module requires membership module!")

if ENABLE_MEMBERSHIP:
    TEMPLATES[0]['OPTIONS']['context_processors'].append('postgresqleu.util.context_processors.member_context')

if 'INVOICE_NOTIFICATION_RECEIVER' not in globals():
    INVOICE_NOTIFICATION_RECEIVER = INVOICE_SENDER_EMAIL

if 'SCHEDULED_JOBS_EMAIL_SENDER' not in globals():
    SCHEDULED_JOBS_EMAIL_SENDER = SCHEDULED_JOBS_EMAIL

ASSETS.update(ASSETS_OVERRIDE)

# NOTE! Turning on the debug toolbar *breaks* manual queries for conferences due to how the
# timezones are handled. Access through the django ORM still works.
if DEBUG and DEBUG_TOOLBAR:
    MIDDLEWARE.append('debug_toolbar.middleware.DebugToolbarMiddleware')
    INSTALLED_APPS.append('debug_toolbar')
