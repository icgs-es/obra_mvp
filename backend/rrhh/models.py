from django.conf import settings
from django.db import models
from django.db.models import Q

from usuarios.models import Team


class GrupoTrabajo(models.Model):
    class TipoGrupo(models.TextChoices):
        OBRA = "OBRA", "Obra"
        ADMINISTRACION = "ADMINISTRACION", "Administración"
        COMERCIAL = "COMERCIAL", "Comercial"
        GERENCIA = "GERENCIA", "Gerencia"
        ARQUITECTURA = "ARQUITECTURA", "Arquitectura"
        SERVICIOS = "SERVICIOS", "Servicios"
        SUBCONTRATA = "SUBCONTRATA", "Subcontrata"
        OTRO = "OTRO", "Otro"

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="rrhh_grupos_trabajo",
    )
    nombre = models.CharField(max_length=160)
    tipo = models.CharField(
        max_length=30,
        choices=TipoGrupo.choices,
        default=TipoGrupo.OTRO,
    )
    descripcion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["team", "tipo", "nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "nombre"],
                name="uniq_rrhh_grupo_team_nombre",
            )
        ]
        indexes = [
            models.Index(fields=["team", "tipo"], name="idx_rrhh_grupo_team_tipo"),
            models.Index(fields=["team", "activo"], name="idx_rrhh_grupo_activo"),
        ]

    def __str__(self):
        return f"{self.team} · {self.nombre}"


class Empleado(models.Model):
    class Situacion(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        BAJA = "BAJA", "Baja"
        INACTIVO = "INACTIVO", "Inactivo"
        OTRO = "OTRO", "Otro"

    class TipoRelacion(models.TextChoices):
        PROPIO = "PROPIO", "Propio"
        AUTONOMO = "AUTONOMO", "Autónomo"
        SUBCONTRATA = "SUBCONTRATA", "Subcontrata"
        EXTERNO = "EXTERNO", "Externo"
        OTRO = "OTRO", "Otro"

    class AreaPrincipal(models.TextChoices):
        OBRA = "OBRA", "Obra"
        ADMINISTRACION = "ADMINISTRACION", "Administración"
        COMERCIAL = "COMERCIAL", "Comercial"
        GERENCIA = "GERENCIA", "Gerencia"
        ARQUITECTURA = "ARQUITECTURA", "Arquitectura"
        SERVICIOS = "SERVICIOS", "Servicios"
        OTRO = "OTRO", "Otro"

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="rrhh_empleados",
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rrhh_empleado",
        help_text="Usuario del sistema asociado, si lo tiene.",
    )

    codigo = models.CharField(max_length=80, blank=True)
    nombre_completo = models.CharField(max_length=220)
    nif_nie = models.CharField(max_length=40, blank=True)
    telefono = models.CharField(max_length=60, blank=True)
    email = models.EmailField(blank=True)

    empresa_empleadora = models.CharField(
        max_length=180,
        blank=True,
        help_text="Empresa real que emplea o factura a esta persona.",
    )
    tipo_relacion = models.CharField(
        max_length=30,
        choices=TipoRelacion.choices,
        default=TipoRelacion.PROPIO,
    )
    area_principal = models.CharField(
        max_length=30,
        choices=AreaPrincipal.choices,
        default=AreaPrincipal.OTRO,
    )

    puesto = models.CharField(max_length=160, blank=True)
    profesion = models.CharField(max_length=160, blank=True)
    situacion = models.CharField(
        max_length=20,
        choices=Situacion.choices,
        default=Situacion.ACTIVO,
    )

    fecha_alta = models.DateField(null=True, blank=True)
    fecha_baja = models.DateField(null=True, blank=True)

    coste_hora = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    precio_bruto_hora = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    coste_bruto_nomina = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    coste_bruto_ss = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sueldo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    coeficiente = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    retencion = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)

    es_fichable = models.BooleanField(default=True)
    es_planificable_obra = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)

    grupos_trabajo = models.ManyToManyField(
        GrupoTrabajo,
        through="EmpleadoGrupoTrabajo",
        related_name="empleados",
        blank=True,
    )

    origen = models.CharField(
        max_length=40,
        blank=True,
        help_text="Origen del dato: manual, seatable, access, importacion, etc.",
    )
    referencia_externa = models.CharField(max_length=120, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["team", "nombre_completo"]
        indexes = [
            models.Index(fields=["team", "situacion"], name="idx_rrhh_emp_situacion"),
            models.Index(fields=["team", "area_principal"], name="idx_rrhh_emp_area"),
            models.Index(fields=["team", "activo"], name="idx_rrhh_emp_activo"),
            models.Index(fields=["team", "nif_nie"], name="idx_rrhh_emp_nif"),
            models.Index(fields=["team", "codigo"], name="idx_rrhh_emp_codigo"),
        ]

    def __str__(self):
        return self.nombre_completo


class EmpleadoGrupoTrabajo(models.Model):
    empleado = models.ForeignKey(
        Empleado,
        on_delete=models.CASCADE,
        related_name="membresias_grupo",
    )
    grupo = models.ForeignKey(
        GrupoTrabajo,
        on_delete=models.CASCADE,
        related_name="membresias",
    )
    rol = models.CharField(max_length=120, blank=True)
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["empleado", "grupo"]
        constraints = [
            models.UniqueConstraint(
                fields=["empleado", "grupo"],
                condition=Q(activo=True),
                name="uniq_rrhh_empleado_grupo_activo",
            )
        ]
        indexes = [
            models.Index(fields=["grupo", "activo"], name="idx_rrhh_memb_grupo_activo"),
            models.Index(fields=["empleado", "activo"], name="idx_rrhh_memb_emp_activo"),
        ]

    def __str__(self):
        return f"{self.empleado} · {self.grupo}"

# ============================================================================
# RRHH_SELECCION_PERSONAL_V1
# ============================================================================

import uuid

from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone


def candidatura_cv_upload_to(instance, filename):
    safe_name = get_valid_filename(filename or "curriculum.pdf")
    team_id = getattr(getattr(instance, "proceso", None), "team_id", "sin_empresa")
    return f"rrhh/seleccion/{team_id}/{uuid.uuid4().hex}_{safe_name}"


class ProcesoSeleccion(models.Model):
    class Estado(models.TextChoices):
        ABIERTO = "ABIERTO", "Abierto"
        PAUSADO = "PAUSADO", "Pausado"
        CERRADO = "CERRADO", "Cerrado"

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="rrhh_procesos_seleccion",
    )
    titulo = models.CharField(max_length=180)
    area = models.CharField(
        max_length=30,
        choices=Empleado.AreaPrincipal.choices,
        default=Empleado.AreaPrincipal.OTRO,
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="procesos_seleccion_responsable",
    )
    descripcion = models.TextField(blank=True)
    requisitos = models.TextField(blank=True)
    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.ABIERTO,
    )
    fecha_apertura = models.DateField(default=timezone.localdate)
    fecha_cierre = models.DateField(null=True, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="procesos_seleccion_creados",
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="procesos_seleccion_modificados",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_apertura", "-id"]
        permissions = [
            ("access_recruitment", "Puede acceder a selección de personal"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["team", "titulo", "fecha_apertura"],
                name="uniq_rrhh_proceso_team_titulo_fecha",
            ),
        ]
        indexes = [
            models.Index(
                fields=["team", "estado"],
                name="idx_rrhh_proc_team_estado",
            ),
            models.Index(
                fields=["responsable", "estado"],
                name="idx_rrhh_proc_resp_estado",
            ),
        ]

    def __str__(self):
        return f"{self.team} · {self.titulo}"


class Candidato(models.Model):
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="rrhh_candidatos",
    )
    nombre_completo = models.CharField(max_length=220)
    telefono = models.CharField(max_length=60, blank=True)
    email = models.EmailField(blank=True)
    ciudad = models.CharField(max_length=120, blank=True)
    perfil_profesional = models.CharField(max_length=220, blank=True)
    linkedin_url = models.URLField(max_length=500, blank=True)
    observaciones = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="candidatos_creados",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["nombre_completo", "id"]
        indexes = [
            models.Index(
                fields=["team", "nombre_completo"],
                name="idx_rrhh_cand_team_nombre",
            ),
            models.Index(
                fields=["team", "email"],
                name="idx_rrhh_cand_team_email",
            ),
        ]

    def __str__(self):
        return self.nombre_completo


class Candidatura(models.Model):
    class Estado(models.TextChoices):
        RECIBIDO = "RECIBIDO", "Recibido"
        REVISADO = "REVISADO", "Revisado"
        PRESELECCIONADO = "PRESELECCIONADO", "Preseleccionado"
        PENDIENTE_LLAMADA = "PENDIENTE_LLAMADA", "Pendiente de llamada"
        # RRHH_SELECCION_ESTADO_CONTACTADO_V1
        CONTACTADO = "CONTACTADO", "Contactado"
        ENTREVISTA_PROGRAMADA = "ENTREVISTA_PROGRAMADA", "Entrevista programada"
        ENTREVISTADO = "ENTREVISTADO", "Entrevistado"
        DESCARTADO = "DESCARTADO", "Descartado"
        SELECCIONADO = "SELECCIONADO", "Seleccionado"
        CONTRATADO = "CONTRATADO", "Contratado"

    class Origen(models.TextChoices):
        LINKEDIN = "LINKEDIN", "LinkedIn"
        INDEED = "INDEED", "Indeed"
        CORREO = "CORREO", "Correo"
        RECOMENDACION = "RECOMENDACION", "Recomendación"
        WEB = "WEB", "Web"
        OTRO = "OTRO", "Otro"

    proceso = models.ForeignKey(
        ProcesoSeleccion,
        on_delete=models.CASCADE,
        related_name="candidaturas",
    )
    candidato = models.ForeignKey(
        Candidato,
        on_delete=models.CASCADE,
        related_name="candidaturas",
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="candidaturas_responsable",
    )
    cv_archivo = models.ForeignKey(
        "archivos.Archivo",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rrhh_candidaturas",
        help_text="Currículo ya existente en el módulo Archivos.",
    )
    cv_fichero = models.FileField(
        upload_to=candidatura_cv_upload_to,
        blank=True,
    )
    cv_nombre_original = models.CharField(max_length=255, blank=True)
    # RRHH_CV_FAST_LOAD_DUPLICATE_DELETE_V1
    cv_sha256 = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )
    origen = models.CharField(
        max_length=30,
        choices=Origen.choices,
        default=Origen.OTRO,
    )
    fecha_solicitud = models.DateField(default=timezone.localdate)
    puntuacion = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    estado = models.CharField(
        max_length=30,
        choices=Estado.choices,
        default=Estado.RECIBIDO,
    )
    fecha_proximo_contacto = models.DateTimeField(null=True, blank=True)
    fecha_entrevista = models.DateTimeField(null=True, blank=True)
    observaciones_revision = models.TextField(blank=True)
    observaciones_entrevista = models.TextField(blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="candidaturas_creadas",
    )
    modificado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="candidaturas_modificadas",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fecha_solicitud", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["proceso", "candidato"],
                name="uniq_rrhh_candidatura_proceso_candidato",
            ),
        ]
        indexes = [
            models.Index(
                fields=["proceso", "estado"],
                name="idx_rrhh_appl_proc_estado",
            ),
            models.Index(
                fields=["responsable", "estado"],
                name="idx_rrhh_appl_resp_estado",
            ),
            models.Index(
                fields=["fecha_proximo_contacto"],
                name="idx_rrhh_appl_contacto",
            ),
            models.Index(
                fields=["fecha_entrevista"],
                name="idx_rrhh_appl_entrevista",
            ),
        ]

    @property
    def team(self):
        return self.proceso.team

    @property
    def cv_disponible(self):
        return bool(self.cv_fichero or self.cv_archivo_id)

    @property
    def cv_nombre(self):
        if self.cv_nombre_original:
            return self.cv_nombre_original
        if self.cv_archivo_id:
            return self.cv_archivo.nombre_original
        if self.cv_fichero:
            return self.cv_fichero.name.rsplit("/", 1)[-1]
        return ""

    def clean(self):
        super().clean()
        if (
            self.proceso_id
            and self.candidato_id
            and self.proceso.team_id != self.candidato.team_id
        ):
            raise ValidationError(
                "El candidato y el proceso deben pertenecer a la misma empresa."
            )
        if (
            self.cv_archivo_id
            and self.proceso_id
            and self.cv_archivo.team_id
            and self.cv_archivo.team_id != self.proceso.team_id
        ):
            raise ValidationError(
                "El currículo vinculado pertenece a otra empresa."
            )
        if self.cv_archivo_id and self.cv_fichero:
            raise ValidationError(
                "Selecciona un currículo existente o sube uno nuevo, no ambos."
            )

    def __str__(self):
        return f"{self.candidato} · {self.proceso.titulo}"


class CandidaturaSeguimiento(models.Model):
    class Tipo(models.TextChoices):
        ALTA = "ALTA", "Alta"
        NOTA = "NOTA", "Nota"
        LLAMADA = "LLAMADA", "Llamada"
        ENTREVISTA = "ENTREVISTA", "Entrevista"
        CAMBIO_ESTADO = "CAMBIO_ESTADO", "Cambio de estado"

    candidatura = models.ForeignKey(
        Candidatura,
        on_delete=models.CASCADE,
        related_name="seguimientos",
    )
    tipo = models.CharField(
        max_length=30,
        choices=Tipo.choices,
        default=Tipo.NOTA,
    )
    fecha = models.DateTimeField(default=timezone.now)
    completado = models.BooleanField(default=False)
    notas = models.TextField(blank=True)
    resultado = models.TextField(blank=True)
    estado_anterior = models.CharField(max_length=30, blank=True)
    estado_nuevo = models.CharField(max_length=30, blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="seguimientos_candidatura",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        indexes = [
            models.Index(
                fields=["candidatura", "-fecha"],
                name="idx_rrhh_seg_cand_fecha",
            ),
            models.Index(
                fields=["tipo", "completado"],
                name="idx_rrhh_seg_tipo_comp",
            ),
        ]

    @property
    def team(self):
        return self.candidatura.proceso.team

    def __str__(self):
        return f"{self.candidatura} · {self.get_tipo_display()}"
