import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PRIVATE_DIR = BASE_DIR / "private"
SECRET_KEY_PATH = PRIVATE_DIR / "secret.key"
if not SECRET_KEY_PATH.is_file():
    raise RuntimeError("Run setup_preview.py to prepare the isolated local preview.")
SECRET_KEY = SECRET_KEY_PATH.read_text(encoding="utf-8").strip()
DEBUG = False
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
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
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": PRIVATE_DIR / "db.sqlite3"}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/members/"
LOGOUT_REDIRECT_URL = "/"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
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
