#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys

from django.conf import global_settings

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

# Django settings for postgresqleu project.

DEBUG = False

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

# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# If running in a Windows environment this must be set to the same as your
# system time zone.
TIME_ZONE = 'Europe/Paris'

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

MIDDLEWARE_CLASSES = [
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'postgresqleu.util.middleware.FilterPersistMiddleware',
    'postgresqleu.util.middleware.RedirectMiddleware',
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
    'django.contrib.admin',
    'django_markwhat',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'postgresqleu._initial',
    'postgresqleu.selectable',
    'postgresqleu.static',
    'postgresqleu.countries',
    'postgresqleu.scheduler.apps.SchedulerAppConfig',
    'postgresqleu.paypal',
    'postgresqleu.adyen',
    'postgresqleu.newsevents',
    'postgresqleu.confreg',
    'postgresqleu.confsponsor',
    'postgresqleu.confwiki',
    'postgresqleu.mailqueue',
    'postgresqleu.invoices',
    'postgresqleu.accounting',
    'postgresqleu.util.apps.UtilAppConfig',
    'postgresqleu.trustlypayment',
    'postgresqleu.braintreepayment',
    'postgresqleu.stripepayment',
    'postgresqleu.transferwise',
    'postgresqleu.membership',
]

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

# Twitter application keys
TWITTER_CLIENT = ""
TWITTER_CLIENTSECRET = ""

# Twitter user keys for the account posting main news
TWITTER_NEWS_TOKEN = ""
TWITTER_NEWS_TOKENSECRET = ""

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

# Reset admins based on confir params from skins and local
ADMINS = (
    ('{0} webmaster'.format(ORG_NAME), DEFAULT_EMAIL),
)
MANAGERS = ADMINS

# Invoice module
# --------------
INVOICE_TITLE_PREFIX = '{0} Invoice'.format(ORG_NAME)
INVOICE_FILENAME_PREFIX = ORG_SHORTNAME.lower()


if GLOBAL_LOGIN_USER:
    MIDDLEWARE_CLASSES.append('postgresqleu.util.middleware.GlobalLoginMiddleware')

if ENABLE_PG_COMMUNITY_AUTH:
    AUTHENTICATION_BACKENDS = (
        'postgresqleu.auth.AuthBackend',
    )
    LOGIN_URL = "{0}/accounts/login/".format(SITEBASE)
4
if ENABLE_ELECTIONS and not ENABLE_MEMBERSHIP:
    raise Exception("Elections module requires membership module!")

if ENABLE_MEMBERSHIP:
    TEMPLATES[0]['OPTIONS']['context_processors'].append('postgresqleu.util.context_processors.member_context')

if ENABLE_ELECTIONS:
    INSTALLED_APPS.append('postgresqleu.elections')

if 'INVOICE_NOTIFICATION_RECEIVER' not in globals():
    INVOICE_NOTIFICATION_RECEIVER = INVOICE_SENDER_EMAIL

if 'SCHEDULED_JOBS_EMAIL_SENDER' not in globals():
    SCHEDULED_JOBS_EMAIL_SENDER = SCHEDULED_JOBS_EMAIL
