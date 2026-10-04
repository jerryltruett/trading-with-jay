import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
PRIVATE_DIR = BASE_DIR / "private"
SECRET_KEY_PATH = PRIVATE_DIR / "secret.key"
JAY_ENV = os.environ.get("JAY_ENV", "local").strip().lower()
if JAY_ENV not in {"local", "production"}:
    raise ImproperlyConfigured("JAY_ENV must be local or production.")
IS_PRODUCTION = JAY_ENV == "production" or os.environ.get("RENDER", "").strip().lower() == "true"
if IS_PRODUCTION:
    SECRET_KEY = os.environ.get("SECRET_KEY", "").strip()
    if (len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5
            or SECRET_KEY.startswith("django-insecure-")):
        raise ImproperlyConfigured("SECRET_KEY must be a generated production secret of at least 50 characters.")
else:
    if not SECRET_KEY_PATH.is_file():
        raise RuntimeError("Run setup_preview.py to prepare the isolated local preview.")
    SECRET_KEY = SECRET_KEY_PATH.read_text(encoding="utf-8").strip()
DEBUG = False
if IS_PRODUCTION:
    ALLOWED_HOSTS = ["tradingwithjay.online", "www.tradingwithjay.online"]
    render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip().lower()
    hostname_pattern = r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if render_hostname:
        if not re.fullmatch(hostname_pattern, render_hostname):
            raise ImproperlyConfigured("RENDER_EXTERNAL_HOSTNAME must contain a DNS hostname without a scheme, path, or wildcard.")
        if render_hostname not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(render_hostname)
    CSRF_TRUSTED_ORIGINS = [f"https://{hostname}" for hostname in ALLOWED_HOSTS]
else:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
    CSRF_TRUSTED_ORIGINS = []
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "community",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
if IS_PRODUCTION:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
ROOT_URLCONF = "jayproject.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "community.identity.account_identity",
    ]},
}]
WSGI_APPLICATION = "jayproject.wsgi.application"
if IS_PRODUCTION:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    try:
        is_postgresql = urlsplit(database_url).scheme.lower() in {"postgres", "postgresql"}
    except ValueError:
        is_postgresql = False
    if not is_postgresql:
        raise ImproperlyConfigured("DATABASE_URL must be a PostgreSQL connection URL in production.")
    import dj_database_url

    try:
        production_database = dj_database_url.parse(
            database_url, conn_max_age=60, conn_health_checks=True, ssl_require=True,
        )
    except (ValueError, KeyError):
        raise ImproperlyConfigured("DATABASE_URL is not a valid PostgreSQL connection URL.") from None
    if not production_database.get("NAME") or not production_database.get("HOST"):
        raise ImproperlyConfigured("DATABASE_URL must include a database name and hostname.")
    DATABASES = {"default": production_database}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": PRIVATE_DIR / "db.sqlite3"}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
if IS_PRODUCTION:
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }
    WHITENOISE_MAX_AGE = 300
    WHITENOISE_AUTOREFRESH = False
    WHITENOISE_USE_FINDERS = False
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/members/"
LOGOUT_REDIRECT_URL = "/"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_SECURE = IS_PRODUCTION
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_SSL_REDIRECT = IS_PRODUCTION
if IS_PRODUCTION:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 65536
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TIME_ZONE = "America/New_York"
LANGUAGE_CODE = "en-us"
USE_TZ = True
CREATOR_USERNAME = "Admin01"
CREATOR_DISPLAY_NAME = "Jay"
PROTECTED_DIR = BASE_DIR / "protected"
STUN_URLS = [url.strip() for url in os.environ.get("JAY_STUN_URLS", "").split(",")
             if url.strip().startswith(("stun:", "stuns:"))]
TURN_URLS = [url.strip() for url in os.environ.get("JAY_TURN_URLS", "").split(",")
             if url.strip().startswith(("turn:", "turns:"))]
TURN_SHARED_SECRET = os.environ.get("JAY_TURN_SHARED_SECRET", "")
