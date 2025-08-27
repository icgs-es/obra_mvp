import os
from pathlib import Path

# 1) Hereda TODO de dev y luego sobrescribe lo necesario para producción
from .dev import *

# 2) Seguridad y modo
DEBUG = False
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", SECRET_KEY if 'SECRET_KEY' in globals() else "change-me")
ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",") if h.strip()]

# 3) HTTPS opcional (útil si de momento vas con IP/HTTP)
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "true").lower() == "true"
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE   = SECURE_SSL_REDIRECT

# 4) CSRF trusted origins (http y https según hosts)
CSRF_TRUSTED_ORIGINS = []
for h in ALLOWED_HOSTS:
    if not h or h == "*":
        continue
    CSRF_TRUSTED_ORIGINS.append(f"https://{h}")
    CSRF_TRUSTED_ORIGINS.append(f"http://{h}")

# 5) Rutas de estáticos/media en contenedor (coinciden con volúmenes del compose)
BASE_DIR = Path(__file__).resolve().parents[2]
STATIC_URL = "/static/"
MEDIA_URL  = "/media/"
STATIC_ROOT = os.getenv("STATIC_ROOT", "/app/staticfiles")
MEDIA_ROOT  = os.getenv("MEDIA_ROOT", "/app/media")

# 6) WhiteNoise para servir estáticos
if "django.middleware.security.SecurityMiddleware" not in MIDDLEWARE:
    MIDDLEWARE.insert(0, "django.middleware.security.SecurityMiddleware")
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    # justo después de SecurityMiddleware
    sec_idx = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
    MIDDLEWARE.insert(sec_idx + 1, "whitenoise.middleware.WhiteNoiseMiddleware")
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# 7) BBDD desde variables de entorno (override)
DATABASES["default"].update({
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.getenv("POSTGRES_DB", DATABASES["default"].get("NAME", "")),
    "USER": os.getenv("POSTGRES_USER", DATABASES["default"].get("USER", "")),
    "PASSWORD": os.getenv("POSTGRES_PASSWORD", DATABASES["default"].get("PASSWORD", "")),
    "HOST": os.getenv("POSTGRES_HOST", DATABASES["default"].get("HOST", "db")),
    "PORT": os.getenv("POSTGRES_PORT", DATABASES["default"].get("PORT", "5432")),
})

# 8) Logging básico en consola (Gunicorn)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
