#!/usr/bin/env python
# -*- coding: utf-8 -*-

from exceptions import ImportError
from django.conf import global_settings

# Django settings for postgresqleu project.

DEBUG = False
TEMPLATE_DEBUG = DEBUG

ADMINS = (
		  ('postgresql.eu webmaster', 'webmaster@postgresql.eu'),
)

MANAGERS = ADMINS

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

# Absolute path to the directory that holds media.
# Example: "/home/media/media.lawrence.com/"
#MEDIA_ROOT = '/home/mha/djangolab/postgresqleu/media'

# URL that handles the media served from MEDIA_ROOT. Make sure to use a
# trailing slash if there is a path component (optional in other cases).
# Examples: "http://media.lawrence.com", "http://example.com/media/"
#MEDIA_URL = '/media/'
STATIC_URL = '/media/'
STATICFILES_DIRS = (
	'../media/',
)

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'zya5w8sfr)i(7q^p3s50-3hk5&4=k(&z6+*1x!#lt#8h%!sizu'

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.Loader',
    'django.template.loaders.app_directories.Loader',
#     'django.template.loaders.eggs.load_template_source',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
	'django.contrib.messages.middleware.MessageMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'postgresqleu.util.middleware.FilterPersistMiddleware',
)


TEMPLATE_CONTEXT_PROCESSORS = global_settings.TEMPLATE_CONTEXT_PROCESSORS + (
	'postgresqleu.util.context_processors.settings_context',
)

ROOT_URLCONF = 'postgresqleu.urls'

TEMPLATE_DIRS = [
	'../template',
	'../../template',
]

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
	'django.contrib.admin',
	'django.contrib.markup',
	'django.contrib.staticfiles',
	'django.contrib.humanize',
	'postgresqleu.static',
	'postgresqleu.countries',
	'postgresqleu.paypal',
	'postgresqleu.adyen',
	'postgresqleu.newsevents',
	'postgresqleu.confreg',
	'postgresqleu.membership',
	'postgresqleu.elections',
	'postgresqleu.mailqueue',
	'postgresqleu.invoicemgr',
	'postgresqleu.invoices',
	'postgresqleu.accounting',
	'postgresqleu.cmutuel',
	'postgresqleu.simplemigrate', # MUST be the last line!
)

INVOICE_SENDER_EMAIL="treasurer@postgresql.eu"
MEMBERSHIP_SENDER_EMAIL="webmaster@postgresql.eu"

# Currency parameter
CURRENCY_ABBREV='EUR'
CURRENCY_SYMBOL='€'

# Module to build PDF invoices
INVOICE_PDF_BUILDER='postgresqleu.util.misc.pgeuinvoice'

# Will be suffixed by " #nnn - <title>"
INVOICE_TITLE_PREFIX='PostgreSQL Europe Invoice'
INVOICE_FILENAME_PREFIX='pgeu'

# Change these when using sandbox!
PAYPAL_BASEURL='https://www.paypal.com/cgi-bin/webscr'
PAYPAL_EMAIL='paypal@postgresql.eu'
PAYPAL_PDT_TOKEN='abc123'
PAYPAL_DEFAULT_SOURCEACCOUNT=1

# Change whether using sandbox or not
ADYEN_BASEURL='https://test.adyen.com/'
ADYEN_CABASEURL='https://test-ca.adyen.com/'
ADYEN_MERCHANTACCOUNT='whatever'
ADYEN_SIGNKEY='foobar'
ADYEN_SKINCODE='abc123'
ADYEN_NOTIFICATION_RECEIVER='somebody@somewhere.com'
ADYEN_NOTIFY_USER='adyennot'
ADYEN_NOTIFY_PASSWORD='topsecret'
ADYEN_REPORT_USER='someone'
ADYEN_REPORT_PASSWORD='topsecret'
ADYEN_MERCHANTREF_PREFIX='PGEU'

# Account numbers used for auto-accounting
ACCOUNTING_PAYPAL_INCOME_ACCOUNT=1932
ACCOUNTING_PAYPAL_FEE_ACCOUNT=6041
ACCOUNTING_PAYPAL_TRANSFER_ACCOUNT=1930
ACCOUNTING_ADYEN_AUTHORIZED_ACCOUNT=1621
ACCOUNTING_ADYEN_PAYABLE_ACCOUNT=1622
ACCOUNTING_ADYEN_FEE_ACCOUNT=6040
ACCOUNTING_ADYEN_PAYOUT_ACCOUNT=1930
ACCOUNTING_ADYEN_MERCHANT_ACCOUNT=1971
ACCOUNTING_ADYEN_REFUNDS_ACCOUNT=2498
ACCOUNTING_MANUAL_INCOME_ACCOUNT=1930
ACCOUNTING_CONFREG_ACCOUNT=3003
ACCOUNTING_MEMBERSHIP_ACCOUNT=3001
ACCOUNTING_DONATIONS_ACCOUNT=3601

# CM balance fetching account
CM_USER_ACCOUNT=None
CM_USER_PASSWORD=None

# Base URLs for generating absolute URLs
SITEBASE="http://www.postgresql.eu"
SITEBASE_SSL="https://www.postgresql.eu"

DISABLE_HTTPS_REDIRECTS=False
DATETIME_FORMAT="Y-m-d H:i:s"
# If there is a local_settings.py, let it override our settings
try:
	from local_settings import *
except ImportError, e:
	pass
