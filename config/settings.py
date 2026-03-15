import os
from pathlib import Path

from dotenv import load_dotenv

from django.utils.translation import gettext_lazy as _

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-key-change-before-production",
)

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'booking',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'booking.middleware.DefaultLanguageMiddleware',
    'booking.middleware.StudioContextMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Route platform models (Studio, Feature, auth…) to 'default' and
# studio-specific models (YogaClass, Booking, Client, SmsReminderLog) to
# their individual per-studio databases.  Studio databases are registered
# dynamically at startup (see booking/apps.py) and on studio creation.
DATABASE_ROUTERS = ['booking.db_router.StudioDatabaseRouter']


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = os.getenv('DJANGO_LANGUAGE_CODE', 'da')

LANGUAGES = [
    ('en', _('English')),
    ('da', _('Danish')),
]

TIME_ZONE = os.getenv('DJANGO_TIME_ZONE', 'Europe/Copenhagen')

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'admin:login'

SMS_GATEWAY_ENABLED = os.getenv('SMS_GATEWAY_ENABLED', 'False').lower() == 'true'
SMS_GATEWAY_URL = os.getenv('SMS_GATEWAY_URL', 'https://api.cpsms.dk/v2/send')
SMS_GATEWAY_USERNAME = os.getenv('SMS_GATEWAY_USERNAME', '')
SMS_GATEWAY_API_KEY = os.getenv('SMS_GATEWAY_API_KEY', '')
SMS_GATEWAY_FROM = os.getenv('SMS_GATEWAY_FROM', 'YogaStudioPlatform')
SMS_GATEWAY_LANGUAGE = os.getenv('SMS_GATEWAY_LANGUAGE', 'da')
SMS_GATEWAY_DEFAULT_COUNTRY_CODE = os.getenv('SMS_GATEWAY_DEFAULT_COUNTRY_CODE', '45')
SMS_GATEWAY_TIMEOUT_SECONDS = int(os.getenv('SMS_GATEWAY_TIMEOUT_SECONDS', '15'))

STUDIO_AUTO_PROVISION_ON_CREATE = os.getenv('STUDIO_AUTO_PROVISION_ON_CREATE', 'True').lower() == 'true'
