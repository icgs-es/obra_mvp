from django.conf import settings
from django.db import models
from django.utils import timezone




# OBRA_MOVIL_INCIDENCIA_MODEL_V1
class IncidenciaObraMovil(models.Model):
    class Tipo(models.TextChoices):
        INCIDENCIA = "INCIDENCIA", "Incidencia"
        SEGURIDAD = "SEGURIDAD", "Seguridad"
        CALIDAD = "CALIDAD", "Calidad"
        SUMINISTRO = "SUMINISTRO", "Suministro"
        MAQUINARIA = "MAQUINARIA", "Maquinaria"
        OTRO = "OTRO", "Otro"

    class Prioridad(models.TextChoices):
        BAJA = "BAJA", "Baja"
        MEDIA = "MEDIA", "Media"
        ALTA = "ALTA", "Alta"
        URGENTE = "URGENTE", "Urgente"

    class Estado(models.TextChoices):
        ABIERTA = "ABIERTA", "Abierta"
        EN_CURSO = "EN_CURSO", "En curso"
        RESUELTA = "RESUELTA", "Resuelta"
        CERRADA = "CERRADA", "Cerrada"

    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.PROTECT,
        related_name="incidencias_obra_movil",
    )
    obra = models.ForeignKey(
        "planificacion_obra.ObraPlanificacion",
        on_delete=models.PROTECT,
        related_name="incidencias_movil",
    )
    unidad_obra = models.ForeignKey(
        "planificacion_obra.UnidadObra",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidencias_movil",
    )
    tarea_obra = models.ForeignKey(
        "planificacion_obra.TareaObra",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidencias_movil",
    )
    empleado = models.ForeignKey(
        "planificacion_obra.EmpleadoObra",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidencias_movil",
    )

    tipo = models.CharField(max_length=30, choices=Tipo.choices, default=Tipo.INCIDENCIA, db_index=True)
    prioridad = models.CharField(max_length=20, choices=Prioridad.choices, default=Prioridad.MEDIA, db_index=True)
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ABIERTA, db_index=True)

    fecha = models.DateField(default=timezone.localdate, db_index=True)
    titulo = models.CharField(max_length=160)
    descripcion = models.TextField()
    resolucion = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidencias_obra_movil_creadas",
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incidencias_obra_movil_cerradas",
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    raw_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        indexes = [
            models.Index(fields=["team", "estado"], name="idx_om_inc_team_estado"),
            models.Index(fields=["team", "fecha"], name="idx_om_inc_team_fecha"),
            models.Index(fields=["obra", "estado"], name="idx_om_inc_obra_estado"),
        ]
        verbose_name = "Incidencia obra móvil"
        verbose_name_plural = "Incidencias obra móvil"

    def __str__(self):
        return f"{self.pk} · {self.estado} · {self.titulo}"
