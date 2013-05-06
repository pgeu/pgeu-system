from exceptions import ImportError

# Django settings for postgresqleu project.

DEBUG = True
TEMPLATE_DEBUG = DEBUG

ADMINS = (
		  ('postgresql.eu webmaster', 'webmaster@postgresql.eu'),
)

MANAGERS = ADMINS

DATABASE_ENGINE = 'postgresql_psycopg2'           # 'postgresql_psycopg2', 'postgresql', 'mysql', 'sqlite3' or 'oracle'.
DATABASE_NAME = 'postgresqleu'             # Or path to database file if using sqlite3.
DATABASE_USER = 'postgresqleu'             # Not used with sqlite3.
DATABASE_PASSWORD = ''         # Not used with sqlite3.
DATABASE_HOST = '/tmp'             # Set to empty string for localhost. Not used with sqlite3.
DATABASE_PORT = ''             # Set to empty string for default. Not used with sqlite3.

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

# URL prefix for admin media -- CSS, JavaScript and images. Make sure to use a
# trailing slash.
# Examples: "http://foo.com/media/", "/media/".
ADMIN_MEDIA_PREFIX = '/admin_media/'

# Make this unique, and don't share it with anybody.
SECRET_KEY = 'zya5w8sfr)i(7q^p3s50-3hk5&4=k(&z6+*1x!#lt#8h%!sizu'

# List of callables that know how to import templates from various sources.
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.load_template_source',
    'django.template.loaders.app_directories.load_template_source',
#     'django.template.loaders.eggs.load_template_source',
)

MIDDLEWARE_CLASSES = (
    'django.middleware.common.CommonMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'postgresqleu.util.middleware.FilterPersistMiddleware',
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
	'postgresqleu.static',
	'postgresqleu.countries',
	'postgresqleu.paypal',
	'postgresqleu.newsevents',
	'postgresqleu.confreg',
	'postgresqleu.membership',
	'postgresqleu.elections',
	'postgresqleu.mailqueue',
	'postgresqleu.invoicemgr',
	'postgresqleu.invoices',
)

INVOICE_SENDER_EMAIL="webmaster@postgresql.eu"

# Change these when using sandbox!
PAYPAL_BASEURL='https://www.paypal.com/cgi-bin/webscr'
PAYPAL_EMAIL='paypal@postgresql.eu'
PAYPAL_PDT_TOKEN='abc123'
PAYPAL_DEFAULT_SOURCEACCOUNT=1

SITEBASE="http://www.postgresql.eu"
SITEBASE_SSL="https://www.postgresql.eu"

DISABLE_HTTPS_REDIRECTS=False
DATETIME_FORMAT="Y-m-d H:i:s"
# If there is a local_settings.py, let it override our settings
try:
	from local_settings import *
except ImportError, e:
	pass
