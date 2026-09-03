import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import models
from django.utils.text import get_valid_filename


def documento_upload_to(instance, filename):
    filename = get_valid_filename(filename or "documento")
    comparativa = instance.oferta.ofertante.comparativa

    return (
        "comparativas/"
        f"{comparativa.team_id}/"
        f"{comparativa.uuid}/"
        f"oferta_{instance.oferta_id}/"
        f"{filename}"
    )


class Comparativa(models.Model):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        EN_COMPARACION = "EN_COMPARACION", "En comparación"
        PENDIENTE_DECISION = (
            "PENDIENTE_DECISION",
            "Pendiente de decisión",
        )
        ADJUDICADA = "ADJUDICADA", "Adjudicada"
        CERRADA = "CERRADA", "Cerrada"

    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    team = models.ForeignKey(
        "usuarios.Team",
        on_delete=models.PROTECT,
        related_name="comparativas",
    )

    titulo = models.CharField(max_length=180)
    categoria = models.CharField(
        max_length=120,
        blank=True,
    )

    estado = models.CharField(
        max_length=30,
        choices=Estado.choices,
        default=Estado.BORRADOR,
        db_index=True,
    )

    descripcion = models.TextField(
        blank=True,
        help_text=(
            "Alcance que deben cubrir las ofertas "
            "para considerarse comparables."
        ),
    )

    # Referencia portable a un objeto externo.
    # En PORTAL INTASA normalmente será una ObraPlanificacion.
    referencia_tipo = models.CharField(
        max_length=120,
        blank=True,
    )
    referencia_id = models.CharField(
        max_length=80,
        blank=True,
    )
    referencia_codigo = models.CharField(
        max_length=120,
        blank=True,
    )
    referencia_nombre = models.CharField(
        max_length=255,
        blank=True,
    )

    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comparativas_responsable",
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comparativas_creadas",
    )

    raw_data = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_index=True,
    )

    class Meta:
        ordering = ("-updated_at", "-id")
        verbose_name = "Comparativa"
        verbose_name_plural = "Comparativas"

        permissions = (
            (
                "access_comparativas",
                "Puede acceder a comparativas",
            ),
        )

        indexes = [
            models.Index(
                fields=("team", "estado"),
                name="cmp_team_estado_idx",
            ),
            models.Index(
                fields=("referencia_tipo", "referencia_id"),
                name="cmp_ref_idx",
            ),
        ]

    def __str__(self):
        return self.titulo


class Ofertante(models.Model):
    class Tipo(models.TextChoices):
        PROVEEDOR = "PROVEEDOR", "Proveedor existente"
        CANDIDATO = "CANDIDATO", "Candidato"

    class Estado(models.TextChoices):
        ACTIVO = "ACTIVO", "Activo"
        ADJUDICADO = "ADJUDICADO", "Adjudicado"
        DESCARTADO = "DESCARTADO", "Descartado"

    comparativa = models.ForeignKey(
        Comparativa,
        on_delete=models.CASCADE,
        related_name="ofertantes",
    )

    tipo = models.CharField(
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.CANDIDATO,
    )

    # Referencia externa intencionadamente sin FK.
    # En INTASA puede apuntar a gestion.Proveedor.
    proveedor_ref_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        db_index=True,
    )

    nombre = models.CharField(max_length=255)
    nif = models.CharField(max_length=60, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=80, blank=True)

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVO,
        db_index=True,
    )

    raw_data = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ("nombre", "id")
        verbose_name = "Ofertante"
        verbose_name_plural = "Ofertantes"

        indexes = [
            models.Index(
                fields=("comparativa", "estado"),
                name="cmp_ofert_comp_idx",
            ),
        ]

    def __str__(self):
        return self.nombre


class Oferta(models.Model):
    class Estado(models.TextChoices):
        RECIBIDA = "RECIBIDA", "Recibida"
        PENDIENTE_ANALISIS = (
            "PENDIENTE_ANALISIS",
            "Pendiente de análisis",
        )
        ANALIZADA = "ANALIZADA", "Analizada"
        REVISAR = "REVISAR", "Revisar alcance"
        VALIDADA = "VALIDADA", "Validada"
        DESCARTADA = "DESCARTADA", "Descartada"

    ofertante = models.ForeignKey(
        Ofertante,
        on_delete=models.CASCADE,
        related_name="ofertas",
    )

    version = models.PositiveIntegerField()

    fecha_documento = models.DateField(
        null=True,
        blank=True,
    )

    referencia = models.CharField(
        max_length=160,
        blank=True,
    )

    moneda = models.CharField(
        max_length=3,
        default="EUR",
    )

    base = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    impuestos = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    estado = models.CharField(
        max_length=30,
        choices=Estado.choices,
        default=Estado.RECIBIDA,
        db_index=True,
    )

    observaciones = models.TextField(blank=True)

    raw_data = models.JSONField(
        default=dict,
        blank=True,
    )

    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comparativas_ofertas_creadas",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ("-version", "-id")
        verbose_name = "Oferta"
        verbose_name_plural = "Ofertas"

        constraints = [
            models.UniqueConstraint(
                fields=("ofertante", "version"),
                name="cmp_oferta_version_unique",
            ),
        ]

        indexes = [
            models.Index(
                fields=("ofertante", "estado"),
                name="cmp_oferta_estado_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.ofertante} · "
            f"V{self.version}"
        )


class DocumentoComparativa(models.Model):
    class EstadoAnalisis(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        PROCESANDO = "PROCESANDO", "Procesando"
        COMPLETADO = "COMPLETADO", "Completado"
        ERROR = "ERROR", "Error"
        NO_APLICA = "NO_APLICA", "No aplica"

    oferta = models.ForeignKey(
        Oferta,
        on_delete=models.CASCADE,
        related_name="documentos",
    )

    archivo = models.FileField(
        upload_to=documento_upload_to,
        max_length=500,
    )

    nombre_original = models.CharField(
        max_length=255,
    )

    extension = models.CharField(
        max_length=20,
        blank=True,
    )

    content_type = models.CharField(
        max_length=160,
        blank=True,
    )

    tamano_bytes = models.PositiveBigIntegerField(
        default=0,
    )

    sha256 = models.CharField(
        max_length=64,
        db_index=True,
    )

    estado_analisis = models.CharField(
        max_length=20,
        choices=EstadoAnalisis.choices,
        default=EstadoAnalisis.PENDIENTE,
        db_index=True,
    )

    texto_extraido = models.TextField(
        blank=True,
    )

    datos_extraidos = models.JSONField(
        default=dict,
        blank=True,
    )

    error_analisis = models.TextField(
        blank=True,
    )

    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comparativas_documentos_subidos",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "Documento de comparativa"
        verbose_name_plural = "Documentos de comparativa"

        indexes = [
            models.Index(
                fields=("oferta", "estado_analisis"),
                name="cmp_doc_estado_idx",
            ),
            models.Index(
                fields=("sha256",),
                name="cmp_doc_sha_idx",
            ),
        ]

    def __str__(self):
        return self.nombre_original


# COMPARATIVAS_V2A_PERSISTENT_CONCEPT_MODEL


class ConceptoOferta(models.Model):
    """
    Concepto documental extraído de una versión concreta
    de una oferta.

    Conserva siempre evidencia del documento original.
    La normalización no sustituye al texto fuente.
    """

    class Alcance(models.TextChoices):
        INCLUIDO = "INCLUIDO", "Incluido"
        EXCLUIDO = "EXCLUIDO", "Excluido"
        INFORMATIVO = "INFORMATIVO", "Informativo"
        REVISAR = "REVISAR", "Revisar"

    class Origen(models.TextChoices):
        DETERMINISTA = (
            "DETERMINISTA",
            "Determinista",
        )
        IA = "IA", "IA"
        HUMANO = "HUMANO", "Humano"

    class Confianza(models.TextChoices):
        MUY_ALTA = "MUY_ALTA", "Muy alta"
        ALTA = "ALTA", "Alta"
        REVISAR = "REVISAR", "Revisar"

    oferta = models.ForeignKey(
        "Oferta",
        on_delete=models.CASCADE,
        related_name="conceptos",
    )

    documento = models.ForeignKey(
        "DocumentoComparativa",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conceptos_extraidos",
    )

    orden = models.PositiveIntegerField(
        default=0,
    )

    codigo_original = models.CharField(
        max_length=120,
        blank=True,
    )

    titulo_original = models.CharField(
        max_length=500,
        blank=True,
    )

    descripcion_original = models.TextField(
        blank=True,
    )

    texto_normalizado = models.TextField(
        blank=True,
    )

    cantidad = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )

    unidad = models.CharField(
        max_length=40,
        blank=True,
    )

    precio_unitario = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
    )

    importe = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )

    alcance = models.CharField(
        max_length=20,
        choices=Alcance.choices,
        default=Alcance.REVISAR,
        db_index=True,
    )

    pagina = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    linea_inicio = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    linea_fin = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    evidencia = models.TextField(
        blank=True,
    )

    origen = models.CharField(
        max_length=20,
        choices=Origen.choices,
        default=Origen.DETERMINISTA,
    )

    confianza_extraccion = models.CharField(
        max_length=20,
        choices=Confianza.choices,
        default=Confianza.REVISAR,
        db_index=True,
    )

    raw_data = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = (
            "oferta_id",
            "orden",
            "id",
        )

        verbose_name = "Concepto de oferta"
        verbose_name_plural = (
            "Conceptos de oferta"
        )

        indexes = [
            models.Index(
                fields=(
                    "oferta",
                    "orden",
                ),
                name="cmp_conc_oferta_ord_idx",
            ),
            models.Index(
                fields=(
                    "documento",
                    "pagina",
                ),
                name="cmp_conc_doc_pag_idx",
            ),
            models.Index(
                fields=(
                    "oferta",
                    "alcance",
                ),
                name="cmp_conc_oferta_alc_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if (
            self.documento_id
            and self.oferta_id
            and self.documento.oferta_id
            != self.oferta_id
        ):
            from django.core.exceptions import (
                ValidationError,
            )

            raise ValidationError(
                {
                    "documento": (
                        "El documento debe pertenecer "
                        "a la misma oferta del concepto."
                    )
                }
            )

        if (
            self.linea_inicio is not None
            and self.linea_fin is not None
            and self.linea_fin
            < self.linea_inicio
        ):
            from django.core.exceptions import (
                ValidationError,
            )

            raise ValidationError(
                {
                    "linea_fin": (
                        "La línea final no puede ser "
                        "anterior a la línea inicial."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()

        return super().save(
            *args,
            **kwargs,
        )

    def __str__(self):
        return (
            self.titulo_original
            or self.texto_normalizado
            or f"Concepto {self.pk or 'nuevo'}"
        )


class GrupoComparacion(models.Model):
    """
    Fila conceptual de la matriz comparativa.

    Un grupo puede relacionar uno o varios conceptos
    de cada oferta. No presupone equivalencia 1:1.
    """

    class Estado(models.TextChoices):
        PROPUESTO = "PROPUESTO", "Propuesto"
        VALIDADO = "VALIDADO", "Validado"
        DESCARTADO = "DESCARTADO", "Descartado"

    class Origen(models.TextChoices):
        DETERMINISTA = (
            "DETERMINISTA",
            "Determinista",
        )
        IA = "IA", "IA"
        HUMANO = "HUMANO", "Humano"

    class Confianza(models.TextChoices):
        MUY_ALTA = "MUY_ALTA", "Muy alta"
        ALTA = "ALTA", "Alta"
        REVISAR = "REVISAR", "Revisar"

    comparativa = models.ForeignKey(
        "Comparativa",
        on_delete=models.CASCADE,
        related_name="grupos_comparacion",
    )

    orden = models.PositiveIntegerField(
        default=0,
    )

    nombre = models.CharField(
        max_length=255,
    )

    descripcion = models.TextField(
        blank=True,
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PROPUESTO,
        db_index=True,
    )

    origen = models.CharField(
        max_length=20,
        choices=Origen.choices,
        default=Origen.DETERMINISTA,
    )

    confianza = models.CharField(
        max_length=20,
        choices=Confianza.choices,
        default=Confianza.REVISAR,
    )

    raw_data = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = (
            "comparativa_id",
            "orden",
            "id",
        )

        verbose_name = "Grupo de comparación"
        verbose_name_plural = (
            "Grupos de comparación"
        )

        indexes = [
            models.Index(
                fields=(
                    "comparativa",
                    "orden",
                ),
                name="cmp_grp_comp_ord_idx",
            ),
            models.Index(
                fields=(
                    "comparativa",
                    "estado",
                ),
                name="cmp_grp_comp_est_idx",
            ),
        ]

    def __str__(self):
        return self.nombre


class RelacionConcepto(models.Model):
    """
    Relación N:M entre una fila canónica de comparación
    y los conceptos documentales que la soportan.

    Permite:
      1 concepto -> varios grupos
      varios conceptos -> 1 grupo
    """

    class Confianza(models.TextChoices):
        MUY_ALTA = "MUY_ALTA", "Muy alta"
        ALTA = "ALTA", "Alta"
        REVISAR = "REVISAR", "Revisar"

    class EstadoRevision(models.TextChoices):
        PROPUESTA = "PROPUESTA", "Propuesta"
        VALIDADA = "VALIDADA", "Validada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    class Origen(models.TextChoices):
        DETERMINISTA = (
            "DETERMINISTA",
            "Determinista",
        )
        IA = "IA", "IA"
        HUMANO = "HUMANO", "Humano"

    grupo = models.ForeignKey(
        "GrupoComparacion",
        on_delete=models.CASCADE,
        related_name="relaciones",
    )

    concepto = models.ForeignKey(
        "ConceptoOferta",
        on_delete=models.CASCADE,
        related_name="relaciones_comparacion",
    )

    confianza_coincidencia = models.CharField(
        max_length=20,
        choices=Confianza.choices,
        default=Confianza.REVISAR,
        db_index=True,
    )

    estado_revision = models.CharField(
        max_length=20,
        choices=EstadoRevision.choices,
        default=EstadoRevision.PROPUESTA,
        db_index=True,
    )

    origen = models.CharField(
        max_length=20,
        choices=Origen.choices,
        default=Origen.DETERMINISTA,
    )

    explicacion = models.TextField(
        blank=True,
    )

    raw_data = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = (
            "grupo_id",
            "id",
        )

        verbose_name = (
            "Relación de concepto"
        )

        verbose_name_plural = (
            "Relaciones de conceptos"
        )

        constraints = [
            models.UniqueConstraint(
                fields=(
                    "grupo",
                    "concepto",
                ),
                name="cmp_rel_grupo_conc_uq",
            ),
        ]

        indexes = [
            models.Index(
                fields=(
                    "grupo",
                    "estado_revision",
                ),
                name="cmp_rel_grp_est_idx",
            ),
            models.Index(
                fields=(
                    "concepto",
                    "estado_revision",
                ),
                name="cmp_rel_conc_est_idx",
            ),
        ]

    def clean(self):
        super().clean()

        if not (
            self.grupo_id
            and self.concepto_id
        ):
            return

        group_comparativa_id = (
            self.grupo.comparativa_id
        )

        concept_comparativa_id = (
            self.concepto
            .oferta
            .ofertante
            .comparativa_id
        )

        if (
            group_comparativa_id
            != concept_comparativa_id
        ):
            from django.core.exceptions import (
                ValidationError,
            )

            raise ValidationError(
                {
                    "concepto": (
                        "El concepto y el grupo deben "
                        "pertenecer a la misma comparativa."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()

        return super().save(
            *args,
            **kwargs,
        )

    def __str__(self):
        return (
            f"{self.grupo} · "
            f"{self.concepto}"
        )
