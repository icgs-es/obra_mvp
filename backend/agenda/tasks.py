from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from .models import Evento

@shared_task
def enviar_recordatorios_eventos():
    now = timezone.now()
    proximos = Evento.objects.filter(inicio__gte=now, inicio__lte=now + timezone.timedelta(minutes=30))
    for e in proximos:
        mins = getattr(e, "recordatorio_min", 0) or 0
        if mins <= 0:
            continue
        delta = (e.inicio - now).total_seconds() / 60.0
        if delta <= mins + 0.5:
            subject = f"Recordatorio: {e.titulo}"
            body = f"Empieza a las {e.inicio.astimezone().strftime('%H:%M')} en {e.ubicacion or '—'}"
            recipients = list(e.asistentes.values_list("email", flat=True))
            creator = getattr(e, "created_by", None)
            if creator and getattr(creator, "email", None):
                recipients.append(creator.email)
            recipients = [r for r in set(recipients) if r]
            if recipients:
                send_mail(subject, body, None, recipients, fail_silently=True)
