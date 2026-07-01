"""
gsa/settings.py  —  one settings file, no splits, no complexity
"""
from pathlib import Path
from datetime import timedelta
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY")
DEBUG      = config("DEBUG", cast=bool, default=True)
#ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost").split(",")
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    # our one and only app
    "school",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "school.middleware.AuditLogMiddleware",
]

ROOT_URLCONF = "gsa.urls"
AUTH_USER_MODEL = "school.User"   # our custom user model

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]

WSGI_APPLICATION = "gsa.wsgi.application"

# ── Database ──────────────────────────────────────────────────────────────────
import dj_database_url          # noqa – install via: pip install dj-database-url
DATABASES = {
    "default": dj_database_url.config(
        default=config("DATABASE_URL"),
        conn_max_age=600,
    )
}

# ── Cache ─────────────────────────────────────────────────────────────────────
# Production: set REDIS_URL in .env  →  redis://127.0.0.1:6379/1
# Development fallback: LocMemCache (single-process only; rate-throttling and
#   cache_page decorators still work but won't be shared across workers).
#
# Install:  pip install django-redis
#
_REDIS_URL = config("REDIS_URL", default="")

if _REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND":  "django_redis.cache.RedisCache",
            "LOCATION": _REDIS_URL,
            "OPTIONS": {
                "CLIENT_CLASS":         "django_redis.client.DefaultClient",
                # Silently degrade if Redis goes down instead of raising
                "IGNORE_EXCEPTIONS":    True,
                # Connection pool — enough headroom for gunicorn workers
                "CONNECTION_POOL_KWARGS": {"max_connections": 50},
            },
            "KEY_PREFIX": "gsa",
            # Keep cached items for 15 minutes by default (matches CACHE_TTL)
            "TIMEOUT": 60 * 15,
        }
    }
    # Use Redis for session storage too when Redis is available
    SESSION_ENGINE     = "django.contrib.sessions.backends.cache"
    SESSION_CACHE_ALIAS = "default"
else:
    # Local dev / CI — no Redis required
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "gsa-locmem",
        }
    }

# ── Auth / JWT ────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "school.pagination.StandardPagination",
    "PAGE_SIZE": 10,
    
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '30/minute',     # Unauthenticated users
        'user': '120/minute',    # Authenticated users
        'auth': '5/minute',      # Strict limit for login/register
    }
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":  timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS":  True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# ── CORS ──────────────────────────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = True   # fine for local dev; restrict in production

# ── Media (profile photos stored locally) ────────────────────────────────────
MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
MAX_UPLOAD_SIZE      = 5 * 1024 * 1024   # 5 MB — raise if needed

# ── Static ────────────────────────────────────────────────────────────────────
STATIC_URL  = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ── Misc ──────────────────────────────────────────────────────────────────────
LANGUAGE_CODE      = "en-us"
TIME_ZONE          = "Africa/Lagos"
USE_I18N           = True
USE_TZ             = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SPECTACULAR_SETTINGS = {
    "TITLE":   "Giant Step Academy API",
    "VERSION": "1.0.0",
}

import sys
if "test" in sys.argv:
    DATABASES["default"] = dj_database_url.config(
        default=config("DATABASE_URL_TEST"),
        conn_max_age=0,
    )