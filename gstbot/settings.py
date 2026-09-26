import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

from gstbot import variant

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-a-secret")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = ["django.contrib.contenttypes", "bot"]
MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]
ROOT_URLCONF = "gstbot.urls"
WSGI_APPLICATION = "gstbot.wsgi.application"

database_url = os.environ.get("DATABASE_URL")
if database_url:
    parsed_database_url = urlsplit(database_url)
    if parsed_database_url.scheme not in {"postgres", "postgresql"}:
        raise ValueError("DATABASE_URL must use the postgres or postgresql scheme")
    database_config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(parsed_database_url.path.lstrip("/")),
        "USER": unquote(parsed_database_url.username or ""),
        "PASSWORD": unquote(parsed_database_url.password or ""),
        "HOST": parsed_database_url.hostname or "",
        "PORT": str(parsed_database_url.port or ""),
    }
else:
    database_config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "gstbot"),
        "USER": os.environ.get("POSTGRES_USER", "gstbot"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "gstbot"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }

DATABASES = {"default": database_config}

USE_TZ = True
TIME_ZONE = "Asia/Kolkata"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TAXMODEL = {
    "BASE_URL": os.environ.get("TAXMODEL_BASE_URL", "http://taxmodel.test"),
    "API_KEY": os.environ.get("TAXMODEL_API_KEY", variant.CANDIDATE_KEY),
    "MODEL": "tax-model-gst",
    "CONNECT_TIMEOUT": 2.0,
    "READ_TIMEOUT": variant.READ_TIMEOUT,
    "MAX_ATTEMPTS": variant.MAX_ATTEMPTS,
    "DEADLINE_S": variant.DEADLINE_S,
    "BACKOFF_BASE_S": 0.5,
    "BACKOFF_CAP_S": 8.0,
    "DAILY_CALL_BUDGET": int(os.environ.get("TAXMODEL_DAILY_CALL_BUDGET", "500")),
    "HISTORY_TURNS": 6,
}

BREAKER = {
    "FAILURE_THRESHOLD": variant.FAILURE_THRESHOLD,
    "OPEN_SECONDS": variant.OPEN_SECONDS,
}
