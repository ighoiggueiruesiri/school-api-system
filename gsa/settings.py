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
