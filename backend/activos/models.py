from django.conf import settings
from django.db import models
from django.utils import timezone

from usuarios.models import Team


class ActivoCore(models.Model):
    ORIGEN_SISTEMA_CHOICES = [
        ("seatable", "SeaTable"),
        ("manual", "Manual"),
        ("importacion", "Importación"),
        ("api", "API"),
        ("otro", "Otro"),
    ]

    TIPO_ACTIVO_CHOICES = [
        ("inmobiliario", "Inmobiliario"),
        ("intasa", "INTASA"),
        ("financiero", "Financiero"),
        ("mobiliario", "Mobiliario"),
        ("vehiculo", "Vehículo"),
        ("otro", "Otro"),
    ]

    ESTADO_OPERATIVO_CHOICES = [
        ("sin_atender", "Sin atender"),
        ("pendiente_visita", "Pendiente visita"),
        ("visitada", "Visitada"),
        ("desestimado", "Desestimado"),
        ("para_ofertar", "Para ofertar"),
        ("buena_atender", "Buena - Atender"),
        ("otro", "Otro"),
    ]

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="activos_core",
        db_index=True,
    )

    nombre = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Nombre legible del activo",
    )

    codigo_externo = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Código externo principal. Ej: ATL_3310_001",
    )

    row_id_externo = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="Row ID único del registro origen en SeaTable",
    )

    origen_sistema = models.CharField(
        max_length=32,
        choices=ORIGEN_SISTEMA_CHOICES,
        default="seatable",
        db_index=True,
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

    tipo_activo = models.CharField(
        max_length=32,
        choices=TIPO_ACTIVO_CHOICES,
        default="inmobiliario",
        db_index=True,
    )

    origen_activo = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text='Valor del desplegable ACTIVO en SeaTable. Ej: ATLAS',
    )

    estado_operativo = models.CharField(
        max_length=32,
        choices=ESTADO_OPERATIVO_CHOICES,
        blank=True,
        default="",
        db_index=True,
        help_text='Normalización del campo Color/estado',
    )

    estado_operativo_raw = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text='Valor bruto original recibido. Ej: "Sin Atender"',
    )

    situacion_activo = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text='Ej: "Pendiente de Cargas"',
    )

    gestor_actual = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activos_core_asignados",
        help_text="Usuario actual responsable del activo",
    )

    gestor_principal = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="Nombre o valor bruto del gestor principal",
    )

    gestores_raw = models.TextField(
        blank=True,
        default="",
        help_text="Contenido bruto completo del campo Gestor",
    )

    historial_resumen = models.TextField(
        blank=True,
        default="",
        help_text="Resumen o contenido bruto del historial",
    )

    direccion = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )
    ciudad = models.CharField(
        max_length=128,
        blank=True,
        default="",
    )
    provincia = models.CharField(
        max_length=128,
        blank=True,
        default="",
    )
    codigo_postal = models.CharField(
        max_length=16,
        blank=True,
        default="",
    )
    pais = models.CharField(
        max_length=64,
        blank=True,
        default="España",
    )

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

    observaciones = models.TextField(
        blank=True,
        default="",
    )

    crm_disponible = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Indica si puede pasar a circuito comercial/CRM",
    )

    crm_activo = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Indica si ya existe como activo usado en CRM",
    )

    fecha_sync = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Última fecha/hora de sincronización",
    )

    sync_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Hash del payload externo para detectar cambios",
    )

    sync_ok = models.BooleanField(
        default=True,
        db_index=True,
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Activo lógico en el sistema",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    # --- Integración SeaTable ---
    seatable_row_id = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="ID de fila origen en SeaTable"
    )

    origen_sync = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Origen de sincronización externa (ej: seatable)"
    )

    sync_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Hash para detectar cambios"
    )

    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Última sincronización desde origen externo"
    )
    class Meta:
        db_table = "activos_core_activo"
        verbose_name = "Activo CORE"
        verbose_name_plural = "Activos CORE"
        ordering = ["-updated_at", "codigo_externo"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "codigo_externo"],
                name="uq_activo_core_team_codigo_externo",
            ),
            models.UniqueConstraint(
                fields=["team", "row_id_externo"],
                name="uq_activo_core_team_row_id_externo",
                condition=~models.Q(row_id_externo=""),
            ),
        ]
        indexes = [
            models.Index(fields=["team", "tipo_activo"]),
            models.Index(fields=["team", "origen_activo"]),
            models.Index(fields=["team", "estado_operativo"]),
            models.Index(fields=["team", "situacion_activo"]),
            models.Index(fields=["team", "crm_disponible"]),
            models.Index(fields=["team", "crm_activo"]),
        ]

    def __str__(self):
        base = self.codigo_externo or f"Activo #{self.pk}"
        if self.nombre:
            return f"{base} - {self.nombre}"
        return base

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

    def marcar_sincronizado(self, hash_value=""):
        self.fecha_sync = timezone.now()
        if hash_value:
            self.sync_hash = hash_value
        self.sync_ok = True