DEBUG = True
DISABLE_HTTPS_REDIRECTS = True
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

SECRET_KEY = 'not-so-secret-test'
SERVER_EMAIL = 'test@example.com'

ALLOWED_HOSTS = ["*"]
SITEBASE = "http://localhost:8080/"

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'pgeu_test',
        # Everything else is configured via environment variables set
        # via the Dockerfiles.
    }
}

# Mount point of the skin inside the Docker containers
SYSTEM_SKIN_DIRECTORY = '/srv/skin'

# Static files configuration.
STATIC_ROOT = '/srv/static/media'
STATICFILES_DIRS = [
    ('', '/srv/pgeu-system/media'),
    ('local', '/srv/skin/media'),
]


# Don't attempt to actually send any email from this development
# environment, but just dump to the console. This will appear in
# the logs of the uwsgi container.
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
