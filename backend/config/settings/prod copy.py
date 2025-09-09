import os
from pathlib import Path

# Hereda SIEMPRE desde base (no desde dev)
from .base import *

# -------------------------
# Núcleo producción
# -------------------------
DEBUG = False

# Secret key
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", SECRET_KEY)

# Hosts
ALLOWED_HOSTS = [
    h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",")
    if h.strip()
]

# -------------------------
# Seguridad (tras proxy)
# -------------------------
# Estás detrás de Caddy/SSL → respeta cabecera X-Forwarded-Proto
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Fuerza HTTPS a Django (si tu proxy ya termina TLS, esto va bien)
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# CSRF Trusted Origins (http y https para cada host listado)
CSRF_TRUSTED_ORIGINS = []
for h in ALLOWED_HOSTS:
    if h and h != "*":
        CSRF_TRUSTED_ORIGINS.append(f"https://{h}")
        CSRF_TRUSTED_ORIGINS.append(f"http://{h}")

# -------------------------
# Archivos estáticos / media
# -------------------------
# OJO: BASE_DIR ya viene de base.py y suele ser /opt/obra_mvp/backend
STATIC_URL = "/static/"
MEDIA_URL  = "/media/"
STATIC_ROOT = os.getenv("STATIC_ROOT", "/app/staticfiles")
MEDIA_ROOT  = os.getenv("MEDIA_ROOT", "/app/media")

# WhiteNoise (sirve estáticos desde Django/Gunicorn si lo necesitas)
if "django.middleware.security.SecurityMiddleware" not in MIDDLEWARE:
    MIDDLEWARE.insert(0, "django.middleware.security.SecurityMiddleware")

# Inserta WhiteNoise justo después de SecurityMiddleware (si no está)
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    sec_idx = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
    MIDDLEWARE.insert(sec_idx + 1, "whitenoise.middleware.WhiteNoiseMiddleware")

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# -------------------------
# Base de datos (variables de entorno)
# -------------------------
DATABASES["default"].update({
    "ENGINE": "django.db.backends.postgresql",
    "NAME":     os.getenv("POSTGRES_DB",     DATABASES["default"].get("NAME", "")),
    "USER":     os.getenv("POSTGRES_USER",   DATABASES["default"].get("USER", "")),
    "PASSWORD": os.getenv("POSTGRES_PASSWORD", DATABASES["default"].get("PASSWORD", "")),
    "HOST":     os.getenv("POSTGRES_HOST",   DATABASES["default"].get("HOST", "db")),
    "PORT":     os.getenv("POSTGRES_PORT",   DATABASES["default"].get("PORT", "5432")),
})

# -------------------------
# Logging
# -------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": { "console": {"class": "logging.StreamHandler"} },
    "root": { "handlers": ["console"], "level": "INFO" },
}

# --- Login global en producción ---
LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/app/"
INTASA_SETTINGS_MARKER = "prod-loaded"