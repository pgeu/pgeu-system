#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys

from exceptions import ImportError
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
    'postgresqleu.paypal',
    'postgresqleu.adyen',
    'postgresqleu.newsevents',
    'postgresqleu.confreg',
    'postgresqleu.confsponsor',
    'postgresqleu.confwiki',
    'postgresqleu.mailqueue',
    'postgresqleu.invoices',
    'postgresqleu.accounting',
    'postgresqleu.util',
]

# Emails
INVOICE_SENDER_EMAIL = DEFAULT_EMAIL
MEMBERSHIP_SENDER_EMAIL = DEFAULT_EMAIL


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

# Membership module
# -----------------
# Years of membership per payment
MEMBERSHIP_LENGTH = 2
# Cost for membership
MEMBERSHIP_COST = 10
# Function called to valide that country is acceptable for membership
MEMBERSHIP_COUNTRY_VALIDATOR = None

# Invoice module
# --------------
INVOICE_PDF_BUILDER = 'postgresqleu.util.misc.baseinvoice.BaseInvoice'
REFUND_PDF_BUILDER = 'postgresqleu.util.misc.baseinvoice.BaseRefund'

# Paypal sandbox configuration
PAYPAL_BASEURL = 'https://www.paypal.com/cgi-bin/webscr'
PAYPAL_EMAIL = DEFAULT_EMAIL
PAYPAL_PDT_TOKEN = 'abc123'
PAYPAL_DEFAULT_SOURCEACCOUNT = 1
PAYPAL_API_USER = 'someuser'
PAYPAL_API_PASSWORD = 'secret'
PAYPAL_API_SIGNATURE = 'secret'
PAYPAL_SANDBOX = True
PAYPAL_REPORT_RECEIVER = DEFAULT_EMAIL
PAYPAL_DONATION_TEXT = "Paypal Donation"

# Adyen configuration
ADYEN_IS_TEST_SYSTEM = True
ADYEN_BASEURL = 'https://test.adyen.com/'
ADYEN_CABASEURL = 'https://test-ca.adyen.com/'
ADYEN_APIBASEURL = 'https://pal-test.adyen.com/'
ADYEN_MERCHANTACCOUNT = 'whatever'
ADYEN_SIGNKEY = 'foobar'
ADYEN_SKINCODE = 'abc123'
ADYEN_NOTIFICATION_RECEIVER = DEFAULT_EMAIL
ADYEN_NOTIFY_USER = 'adyennot'
ADYEN_NOTIFY_PASSWORD = 'topsecret'
ADYEN_REPORT_USER = 'someone'
ADYEN_REPORT_PASSWORD = 'topsecret'
ADYEN_WS_USER = 'someone'
ADYEN_WS_PASSWORD = 'topsecret'
ADYEN_MERCHANTREF_PREFIX = 'PGEU'
ADYEN_MERCHANTREF_REFUND_PREFIX = 'PGEUREFUND'

# Account numbers used for auto-accounting
ENABLE_AUTO_ACCOUNTING = False
ACCOUNTING_PAYPAL_INCOME_ACCOUNT = 1932
ACCOUNTING_PAYPAL_FEE_ACCOUNT = 6041
ACCOUNTING_PAYPAL_TRANSFER_ACCOUNT = 1930
ACCOUNTING_ADYEN_AUTHORIZED_ACCOUNT = 1621
ACCOUNTING_ADYEN_PAYABLE_ACCOUNT = 1622
ACCOUNTING_ADYEN_FEE_ACCOUNT = 6040
ACCOUNTING_ADYEN_PAYOUT_ACCOUNT = 1930
ACCOUNTING_ADYEN_MERCHANT_ACCOUNT = 1971
ACCOUNTING_ADYEN_REFUNDS_ACCOUNT = 2498
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
ENABLE_NEWS = True
ENABLE_MEMBERSHIP = False
ENABLE_ELECTIONS = False
ENABLE_BRAINTREE = False
ENABLE_TRUSTLY = False

# Set to a username and password in local_settings.py to enable global http auth
GLOBAL_LOGIN_USER = ''
GLOBAL_LOGIN_PASSWORD = ''

# Treasurer email address
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
    (u'{0} webmaster'.format(ORG_NAME), DEFAULT_EMAIL),
)
MANAGERS = ADMINS

# Invoice module
# --------------
INVOICE_TITLE_PREFIX = u'{0} Invoice'.format(ORG_NAME)
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
    INSTALLED_APPS.append('postgresqleu.membership')
    TEMPLATES[0]['OPTIONS']['context_processors'].append('postgresqleu.util.context_processors.member_context')

if ENABLE_ELECTIONS:
    INSTALLED_APPS.append('postgresqleu.elections')


if ENABLE_BRAINTREE:
    INSTALLED_APPS.append('postgresqleu.braintreepayment')
    BRAINTREE_SANDBOX = False
    # Accounts to use for braintree transactions
    # Override in local_settings.py, and also configure
    # the public and secret keys there.
    ACCOUNTING_BRAINTREE_AUTHORIZED_ACCOUNT = 1621
    ACCOUNTING_BRAINTREE_PAYABLE_ACCOUNT = 1623
    ACCOUNTING_BRAINTREE_PAYOUT_ACCOUNT = 1930
    ACCOUNTING_BRAINTREE_FEE_ACCOUNT = 6040

if ENABLE_TRUSTLY:
    INSTALLED_APPS.append('postgresqleu.trustlypayment')

    # Accounts to use for trustly transactions
    ACCOUNTING_TRUSTLY_ACCOUNT = 1972
