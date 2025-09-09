from pathlib import Path
import os

# BASE_DIR apunta a /opt/obra_mvp/backend/
BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = "dev-key"
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    # Django apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Terceros
    "rest_framework",

    # Apps propias
    "apps.frontend",
    "apps.core",
    "portal",
    "agenda",
    "tareas",
    "usuarios",
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

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",               # /app/backend/templates
            BASE_DIR / "portal" / "templates",    # <-- AÑADIR ESTA LÍNEA
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "obradb"),
        "USER": os.environ.get("DB_USER", "obradb"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "obradb"),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": int(os.environ.get("DB_PORT", "5432")),
    }
}

LANGUAGE_CODE = "es-es"
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
