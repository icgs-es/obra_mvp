from django.conf import settings
from django.db import models
from django.utils import timezone


class ActividadPlataforma(models.Model):
    class Visibilidad(models.TextChoices):
        ACTOR = "ACTOR", "Solo actor"
        EQUIPO = "EQUIPO", "Equipo"
        OBJETO = "OBJETO", "Según permisos del objeto"

    class Origen(models.TextChoices):
        EXPLICITO = "EXPLICITO", "Servicio explícito"
        SENAL = "SENAL", "Señal Django"
        IMPORTACION = "IMPORTACION", "Importación"
        SISTEMA = "SISTEMA", "Sistema"

    team = models.ForeignKey(
        "usuarios.Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="actividades_plataforma",
    )

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="actividades_plataforma",
    )

    modulo = models.CharField(
        max_length=50,
        db_index=True,
    )

    accion = models.CharField(
        max_length=50,
        db_index=True,
    )

    tipo_objeto = models.CharField(
        max_length=100,
        blank=True,
    )

    objeto_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    objeto_repr = models.CharField(
        max_length=255,
        blank=True,
    )

    descripcion = models.TextField(
        blank=True,
    )

    url = models.CharField(
        max_length=500,
        blank=True,
    )

    visibilidad = models.CharField(
        max_length=20,
        choices=Visibilidad.choices,
        default=Visibilidad.EQUIPO,
        db_index=True,
    )

    origen = models.CharField(
        max_length=20,
        choices=Origen.choices,
        default=Origen.EXPLICITO,
        db_index=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    agrupacion_key = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )

    clave_idempotencia = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
    )

    visible_en_dashboard = models.BooleanField(
        default=True,
        db_index=True,
    )

    ocurrida_en = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ("-ocurrida_en", "-id")
        verbose_name = "Actividad de plataforma"
        verbose_name_plural = "Actividades de plataforma"

        permissions = (
            (
                "view_team_activity",
                "Puede ver la actividad de su equipo",
            ),
            (
                "view_all_activity",
                "Puede ver toda la actividad permitida",
            ),
        )

        indexes = [
            models.Index(
                fields=("team", "-ocurrida_en"),
                name="act_team_fecha_idx",
            ),
            models.Index(
                fields=("actor", "-ocurrida_en"),
                name="act_actor_fecha_idx",
            ),
            models.Index(
                fields=("modulo", "-ocurrida_en"),
                name="act_mod_fecha_idx",
            ),
            models.Index(
                fields=("accion", "-ocurrida_en"),
                name="act_acc_fecha_idx",
            ),
            models.Index(
                fields=("team", "modulo", "-ocurrida_en"),
                name="act_team_mod_fecha_idx",
            ),
            models.Index(
                fields=("agrupacion_key", "-ocurrida_en"),
                name="act_group_fecha_idx",
            ),
        ]

    def __str__(self):
        actor = self.actor.get_username() if self.actor_id else "Sistema"
        objeto = self.objeto_repr or self.tipo_objeto or "actividad"
        return f"{actor} · {self.accion} · {objeto}"
