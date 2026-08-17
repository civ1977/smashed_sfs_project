"""
Django settings for smashed_sfs project.
"""

import os
import sys
from pathlib import Path
import pymysql
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured
pymysql.install_as_MySQLdb()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Local, gitignored secrets (DB credentials, etc.) live in .env - see
# .env.example for the expected keys. Real environment variables (e.g. set
# by a hosting platform) still take precedence over anything in .env.
load_dotenv(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
# Override with a DJANGO_SECRET_KEY environment variable for any real
# deployment; this fallback is fine for local dev only.
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    '4@l5)1et3s9$4sy!xrcz2y5gxmtx(1(7qv)z+7_3(iuv)2i9la',
)

# SECURITY WARNING: don't run with debug turned on in production!
# Set DJANGO_DEBUG=False in the environment before exposing this past localhost
# (e.g. through a cloudflared tunnel) - with DEBUG on, any unhandled error
# renders a full stack trace + settings dump to whoever triggers it.
DEBUG = os.environ.get('DJANGO_DEBUG', 'True') == 'True'

ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
# For tunnel testing, set DJANGO_ALLOWED_HOSTS (comma-separated) in the
# environment for that session instead of committing a wildcard here.
_extra_hosts = os.environ.get('DJANGO_ALLOWED_HOSTS')
if _extra_hosts:
    ALLOWED_HOSTS += [h.strip() for h in _extra_hosts.split(',') if h.strip()]

# Django checks the request's Origin header against this list for any POST
# (login, etc.); a tunnel's domain needs to be added here for that session
# via DJANGO_CSRF_TRUSTED_ORIGINS (comma-separated, include the scheme, e.g.
# "https://your-subdomain.trycloudflare.com") or POSTs through it get
# rejected as a possible CSRF attack even though ALLOWED_HOSTS permits it.
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'students',
    'grades',
    'reports',
    'school',
    'portal',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Serves collected static files directly from the app process - runserver
    # only does this itself while DEBUG=True, so without whitenoise a
    # DEBUG=False deployment would serve pages with no CSS/JS at all unless
    # a separate web server (nginx, etc.) is set up to handle /static/.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'smashed_sfs.middleware.TrackLastSeenMiddleware',
    'smashed_sfs.middleware.TrackSiteVisitMiddleware',
]

ROOT_URLCONF = 'smashed_sfs.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'smashed_sfs.context_processors.shell_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'smashed_sfs.wsgi.application'

# Database
# No hardcoded credentials and no root: DB_USER/DB_PASSWORD must come from
# .env (or a real environment variable), and should name a least-privilege
# MySQL user scoped to just this database - see .env.example and
# CLAUDE.md/README for the CREATE USER / GRANT statement. `manage.py test`
# below overrides this with an isolated in-memory SQLite database instead,
# so these are never required just to run the test suite.
_DB_USER = os.environ.get('DB_USER')
_DB_PASSWORD = os.environ.get('DB_PASSWORD')
if ('test' not in sys.argv) and (not _DB_USER or not _DB_PASSWORD):
    raise ImproperlyConfigured(
        'DB_USER and DB_PASSWORD are not set. Copy .env.example to .env and fill in '
        'a least-privilege MySQL user for this database (not root) - see CLAUDE.md/'
        'README for the CREATE USER / GRANT statement to create one.'
    )

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'smashed_sfs',
        'USER': _DB_USER,
        'PASSWORD': _DB_PASSWORD,
        'HOST': 'localhost',
        'PORT': '3306',
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }
}

# `manage.py test` builds a brand-new database from scratch. The full
# migration history used to fail replaying from an empty database (several
# historical migrations only worked against the one real, already-manually-
# patched MySQL database - see CLAUDE.md's "Migration history vs. real
# schema" note for the full story and how it was fixed) - that's fixed now
# and a real from-scratch `migrate` against MySQL does work. Tests still
# route around it anyway: an isolated in-memory SQLite database with
# migration replay skipped entirely (tables built straight from the current
# models.py, a standard Django testing pattern) is simply faster and fully
# isolated from the real MySQL database, which is worth keeping regardless.
if 'test' in sys.argv:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }

    class _DisableMigrations:
        def __contains__(self, item):
            return True

        def __getitem__(self, item):
            return None

    MIGRATION_MODULES = _DisableMigrations()

# Email (used for the password-reset flow). Defaults to printing emails to
# the console so reset links work out of the box with zero setup - set
# EMAIL_HOST/EMAIL_HOST_USER/EMAIL_HOST_PASSWORD (e.g. a Gmail address with
# an App Password, smtp.gmail.com port 587 with EMAIL_USE_TLS=True) to
# actually send real emails.
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'no-reply@smashed-sfs.local')

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
# Target dir for `manage.py collectstatic`, which whitenoise then serves from
# - only needed for a DEBUG=False deployment; local runserver never uses it.
STATIC_ROOT = BASE_DIR / 'staticfiles'
# CompressedManifestStaticFilesStorage requires `collectstatic` to have
# already run - {% static %} tags resolve through its manifest file even
# in dev/tests - so it's only used once DEBUG=False (a real deployment,
# where collectstatic is expected to run first). Local runserver and tests
# keep using the plain storage that serves straight from STATICFILES_DIRS
# with no build step.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': (
            'django.contrib.staticfiles.storage.StaticFilesStorage' if DEBUG
            else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
        ),
    },
}

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Login/Logout settings
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# Logging. With DEBUG=True, unhandled errors already show Django's own
# debug page, so console output here mostly matters once DEBUG=False (no
# debug page - errors would otherwise vanish silently). Also writes ERROR+
# to a rotating file so they're not lost once the console itself isn't
# being watched. LOGS_DIR is created on import since Django's FileHandler
# doesn't create its own parent directory.
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'django.log',
            'maxBytes': 5 * 1024 * 1024,
            'backupCount': 5,
            'formatter': 'verbose',
            'level': 'ERROR',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django.security.DisallowedHost': {
            # ALLOWED_HOSTS rejections are expected background noise from
            # internet scanners once this is ever reachable off localhost -
            # still logged, just not at the level that pages anyone.
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}