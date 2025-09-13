import os
from celery import Celery

# Usa prod en tu despliegue (si quieres puedes dejarlo sin hardcodear)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

app = Celery("obra")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
