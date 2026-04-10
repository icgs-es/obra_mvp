from django.conf import settings
from django.db import models
from django.utils import timezone


class Calendar(models.Model):
    TIPO_CHOICES = (
        ("PERSONAL", "Personal"),
        ("DEPARTAMENTO", "Departamento"),
        ("GLOBAL", "Global"),
    )

    nombre = models.CharField("Nombre", max_length=200, default="Calendario")

    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default="PERSONAL",
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="calendars",
    )

    departamento = models.CharField(max_length=100, blank=True, null=True)

    activo = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.nombre} ({self.tipo})"


class Event(models.Model):
    class TaskStatus(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        EN_PROCESO = "EN_PROCESO", "En proceso"
        BLOQUEADA = "BLOQUEADA", "Bloqueada"
        COMPLETADO = "COMPLETADO", "Completado"
        CANCELADO = "CANCELADO", "Cancelado"

    class Visibility(models.TextChoices):
        PRIVADA = "PRIVADA", "Privada"
        DEPARTAMENTO = "DEPARTAMENTO", "Departamento"
        GLOBAL = "GLOBAL", "Global"

    title = models.CharField("Título", max_length=255)
    calendar = models.ForeignKey(Calendar, on_delete=models.PROTECT, related_name="events")

    start = models.DateTimeField("Desde")
    end = models.DateTimeField("Hasta", null=True, blank=True)
    all_day = models.BooleanField("Todo el día", default=False)

    rrule = models.TextField("Se repite (RRULE)", blank=True, default="")
    rrule_until = models.DateTimeField("Repetir hasta", null=True, blank=True)

    who_text = models.CharField("Quién (texto libre)", max_length=255, blank=True, default="")
    who_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="agenda_events")

    description = models.TextField("Descripción", blank=True, default="")

    status = models.CharField(
        "Estado tarea",
        max_length=20,
        choices=TaskStatus.choices,
        default=TaskStatus.PENDIENTE,
    )

    location = models.CharField("Dónde", max_length=255, blank=True, default="")

    visibility = models.CharField(
        "Visibilidad",
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PRIVADA,
    )

    obra_id = models.IntegerField(null=True, blank=True)
    obra_nombre = models.CharField(max_length=255, blank=True, default="")

    team = models.ForeignKey("usuarios.Team", null=True, blank=True, on_delete=models.SET_NULL)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events_updated",
    )
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-start", "-created_at")

    def __str__(self):
        return self.title


class Reminder(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="reminders")
    # minutos antes del inicio; negativo no permitido
    minutes_before = models.PositiveIntegerField(default=15)
    # canal: email / web / push / sms (de momento email+web)
    channel = models.CharField(max_length=20, default="email")  # "email" | "web"


class Attachment(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="agenda/attachments/")
    name = models.CharField(max_length=255, blank=True, default="")
