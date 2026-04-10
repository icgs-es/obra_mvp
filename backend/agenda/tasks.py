from celery import shared_task
from django.utils import timezone
from django.core.mail import send_mail
from .models import Event
import logging

log = logging.getLogger(__name__)

@shared_task
def enviar_recordatorios_eventos():
    """Envía recordatorios por email para eventos próximos.

    Lógica:
    - Busca eventos con start entre ahora y 30 minutos.
    - Determina minutos de recordatorio: si el evento tiene Reminder(email), usa el mínimo; si no, 15.
    - Envía solo cuando round(delta_minutos) coincide con el minuto de recordatorio (evita duplicados en el beat cada 60s).
    """
    now = timezone.now()

    proximos = Event.objects.filter(
        start__gte=now,
        start__lte=now + timezone.timedelta(minutes=30),
    )

    enviados = 0
    for e in proximos:
        try:
            # Determinar minutos de recordatorio
            mins = 15
            try:
                qs = e.reminders.filter(channel="email").values_list("minutes_before", flat=True)
                if qs:
                    mins = min(qs)
            except Exception:
                pass

            delta = (e.start - now).total_seconds() / 60.0
            if round(delta) != mins:
                continue

            titulo = e.title or "Evento"
            ubicacion = (e.location or "—")
            subject = f"Recordatorio: {titulo}"
            body = f"Empieza a las {e.start.astimezone().strftime('%H:%M')} en {ubicacion}"

            recipients = set()
            try:
                recipients.update(list(e.who_users.values_list("email", flat=True)))
            except Exception:
                pass

            if e.created_by and getattr(e.created_by, "email", None):
                recipients.add(e.created_by.email)

            recipients = [r for r in recipients if r]
            if recipients:
                send_mail(subject, body, None, recipients, fail_silently=True)
                enviados += 1
        except Exception as ex:
            log.warning("Fallo recordatorio evento %s: %s", getattr(e, "id", "?"), ex)

    if enviados:
        log.info("Recordatorios enviados: %s", enviados)

