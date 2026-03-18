from django.db import models
from django.utils import timezone

from usuarios.models import Team

class Activo(models.Model):
    """
    Modelo canónico inicial para activos sincronizados desde SeaTable.
    Fase 1:
    - SeaTable es el origen maestro
    - INTASA refleja, consulta y estructura
    - Los campos vinculados (valoraciones, visitas, cargas, demandas)
      se guardan en bruto para normalizarlos en fase 2
    """

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="activos",
        db_index=True,
    )

    # Identificación interna / externa
    codigo_externo = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Ej: ATL_3310_001",
    )
    row_id_externo = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Row ID único de SeaTable",
    )

    # Trazabilidad de origen
    origen = models.CharField(
        max_length=50,
        default="seatable",
        db_index=True,
        help_text="Sistema origen del registro. Ej: seatable",
    )
    base_origen = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text='Ej: "ACTIVOS INTASA"',
    )
    tabla_origen = models.CharField(
        max_length=150,
        blank=True,
        default="",
        help_text='Ej: "TODOS LOS ACTIVOS"',
    )

    # Campo SeaTable "ACTIVO" (no booleano)
    origen_activo = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text='Valor del desplegable "ACTIVO". Ej: ATLAS',
    )

    # Campo SeaTable "Color"
    estado_operativo = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text='Ej: Sin Atender, Visitada, Desestimado, Para Ofertar',
    )

    # Campo gestor: por ahora texto bruto, porque en SeaTable puede venir
    # como nombre, varios nombres o ids internos
    gestor_principal = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Gestor principal o contenido bruto del campo Gestor",
    )

    # Campos descriptivos
    historial_resumen = models.TextField(
        blank=True,
        default="",
        help_text="Contenido bruto/resumen del campo Historial",
    )
    situacion_activo = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text='Ej: Pendiente de Cargas, Pendiente de Jaime, etc.',
    )
    observaciones = models.TextField(
        blank=True,
        default="",
    )

    # Campos vinculados a otras tablas en SeaTable
    # Fase 1: guardados en bruto
    valoraciones_raw = models.TextField(
        blank=True,
        default="",
        help_text='Ej: "V-000108, V-000544"',
    )
    visitas_raw = models.TextField(
        blank=True,
        default="",
        help_text='Ej: "VI-0107, VI-0108"',
    )
    cargas_raw = models.TextField(
        blank=True,
        default="",
        help_text='Ej: "C-0239, C-0240"',
    )
    demandas_raw = models.TextField(
        blank=True,
        default="",
        help_text='Ej: "D-010, D-011"',
    )

    # Control de sincronización
    fecha_sync = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Última fecha/hora de sincronización desde SeaTable",
    )
    sync_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Hash del payload sincronizado para detectar cambios",
    )
    sync_ok = models.BooleanField(
        default=True,
        db_index=True,
    )

    # Control interno
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Activo lógico en INTASA, no confundir con el campo ACTIVO de SeaTable",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "activos_activo"
        ordering = ["-updated_at", "codigo_externo"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "codigo_externo"],
                name="uq_activo_team_codigo_externo",
            ),
            models.UniqueConstraint(
                fields=["team", "row_id_externo"],
                name="uq_activo_team_row_id_externo",
            ),
        ]
        indexes = [
            models.Index(fields=["team", "origen_activo"]),
            models.Index(fields=["team", "estado_operativo"]),
            models.Index(fields=["team", "situacion_activo"]),
            models.Index(fields=["team", "codigo_externo"]),
        ]

    def __str__(self):
        return f"{self.codigo_externo} - {self.origen_activo or 'SIN_ORIGEN'}"

    @property
    def valoraciones_list(self):
        return [x.strip() for x in self.valoraciones_raw.split(",") if x.strip()]

    @property
    def visitas_list(self):
        return [x.strip() for x in self.visitas_raw.split(",") if x.strip()]

    @property
    def cargas_list(self):
        return [x.strip() for x in self.cargas_raw.split(",") if x.strip()]

    @property
    def demandas_list(self):
        return [x.strip() for x in self.demandas_raw.split(",") if x.strip()]

    def marcar_sincronizado(self, hash_value: str = ""):
        self.fecha_sync = timezone.now()
        if hash_value:
            self.sync_hash = hash_value
        self.sync_ok = True