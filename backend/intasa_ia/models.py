import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .private_storage import private_ia_storage


class ConversacionIA(models.Model):
    class Estado(models.TextChoices):
        ACTIVA = "ACTIVA", "Activa"
        ARCHIVADA = "ARCHIVADA", "Archivada"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversaciones_intasa_ia",
    )

    # Campo opcional conservado para futuras consultas empresariales.
    # La conversación ya no depende de una empresa.
    team = models.ForeignKey(
        "usuarios.Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversaciones_intasa_ia",
    )

    titulo = models.CharField(
        max_length=160,
        default="Nueva conversación",
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVA,
        db_index=True,
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
        verbose_name = "Conversación INTASA IA"
        verbose_name_plural = "Conversaciones INTASA IA"

        permissions = (
            (
                "use_intasa_ia",
                "Puede utilizar INTASA IA",
            ),
            (
                "view_all_ia_conversations",
                "Puede consultar todas las conversaciones IA",
            ),
        )

        indexes = [
            models.Index(
                fields=("user", "-updated_at"),
                name="ia_conv_usr_upd",
            ),
            models.Index(
                fields=("team", "-updated_at"),
                name="ia_conv_team_upd",
            ),
        ]

    def __str__(self):
        return f"{self.user} · {self.titulo}"


class MensajeIA(models.Model):
    class Rol(models.TextChoices):
        USUARIO = "USUARIO", "Usuario"
        ASISTENTE = "ASISTENTE", "Asistente"
        SISTEMA = "SISTEMA", "Sistema"

    conversacion = models.ForeignKey(
        ConversacionIA,
        on_delete=models.CASCADE,
        related_name="mensajes",
    )

    rol = models.CharField(
        max_length=20,
        choices=Rol.choices,
        db_index=True,
    )

    contenido = models.TextField()

    proveedor = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )

    modelo = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    request_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
    )

    tokens_entrada = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    tokens_salida = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = ("created_at", "id")
        verbose_name = "Mensaje INTASA IA"
        verbose_name_plural = "Mensajes INTASA IA"

        indexes = [
            models.Index(
                fields=("conversacion", "created_at"),
                name="ia_msg_conv_fecha",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_rol_display()} · "
            f"{self.contenido[:80]}"
        )


class AccesoConversacionIA(models.Model):
    """
    Permite compartir una conversación completa.

    V1C: el acceso compartido es exclusivamente de lectura.
    """

    conversacion = models.ForeignKey(
        ConversacionIA,
        on_delete=models.CASCADE,
        related_name="accesos_compartidos",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="accesos_conversaciones_intasa_ia",
    )

    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversaciones_intasa_ia_compartidas",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = ("-created_at", "-id")
        verbose_name = "Acceso compartido INTASA IA"
        verbose_name_plural = "Accesos compartidos INTASA IA"

        constraints = [
            models.UniqueConstraint(
                fields=("conversacion", "user"),
                name="ia_share_unique",
            ),
        ]

        indexes = [
            models.Index(
                fields=("user", "-created_at"),
                name="ia_share_usr_fecha",
            ),
            models.Index(
                fields=("conversacion", "user"),
                name="ia_share_conv_usr",
            ),
        ]

    def __str__(self):
        return (
            f"{self.conversacion_id} → "
            f"{self.user}"
        )


def adjunto_ia_upload_to(instance, filename):
    return f"attachments/{instance.pk.hex}{instance.extension}"


class AdjuntoIA(models.Model):
    class Estado(models.TextChoices):
        UPLOADED = "UPLOADED", "Subiendo"
        PROCESSING = "PROCESSING", "Procesando"
        READY = "READY", "Disponible para analizar"
        FAILED = "FAILED", "No se pudo procesar"
        DELETED = "DELETED", "Eliminado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        ConversacionIA, on_delete=models.CASCADE, related_name="adjuntos"
    )
    message = models.ForeignKey(
        MensajeIA, on_delete=models.CASCADE, related_name="adjuntos"
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="adjuntos_intasa_ia",
    )
    file = models.FileField(
        storage=private_ia_storage,
        upload_to=adjunto_ia_upload_to,
        max_length=255,
    )
    original_name = models.CharField(max_length=255)
    safe_display_name = models.CharField(max_length=255)
    declared_mime = models.CharField(max_length=127)
    detected_mime = models.CharField(max_length=127)
    extension = models.CharField(max_length=10)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=16, choices=Estado.choices, default=Estado.UPLOADED, db_index=True
    )
    error_code = models.CharField(max_length=64, blank=True, default="")
    processing_method = models.CharField(max_length=32, blank=True, default="")
    extracted_text = models.TextField(blank=True, default="")
    technical_summary = models.CharField(max_length=500, blank=True, default="")
    page_count = models.PositiveIntegerField(null=True, blank=True)
    sheet_count = models.PositiveIntegerField(null=True, blank=True)
    ocr_used = models.BooleanField(default=False)
    extractor_version = models.CharField(max_length=32, blank=True, default="")
    processed_source_sha256 = models.CharField(max_length=64, blank=True, default="")
    invoice_analysis = models.JSONField(default=dict, blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at", "id")
        indexes = [
            models.Index(fields=("conversation", "created_at"), name="ia_att_conv_created"),
            models.Index(fields=("message", "created_at"), name="ia_att_msg_created"),
        ]

    def clean(self):
        super().clean()
        if self.message_id and self.conversation_id:
            message_conversation_id = (
                self.message.conversacion_id
                if "message" in self._state.fields_cache
                else MensajeIA.objects.filter(pk=self.message_id).values_list(
                    "conversacion_id", flat=True
                ).first()
            )
            if message_conversation_id != self.conversation_id:
                raise ValidationError(
                    {"message": "El mensaje y el adjunto deben pertenecer a la misma conversación."}
                )

    def __str__(self):
        return self.safe_display_name


class ProcesamientoMensajeIA(models.Model):
    class Estado(models.TextChoices):
        QUEUED = "QUEUED", "En cola"
        PROCESSING = "PROCESSING", "Procesando"
        GENERATING = "GENERATING", "Generando respuesta"
        COMPLETED = "COMPLETED", "Completado"
        FAILED = "FAILED", "Fallido"

    message = models.OneToOneField(
        MensajeIA, on_delete=models.CASCADE, related_name="document_processing"
    )
    status = models.CharField(
        max_length=16, choices=Estado.choices, default=Estado.QUEUED, db_index=True
    )
    task_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    generation_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    assistant_message = models.OneToOneField(
        MensajeIA, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="generated_from_documents",
    )
    error_code = models.CharField(max_length=64, blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Procesamiento documental INTASA IA"
        verbose_name_plural = "Procesamientos documentales INTASA IA"


class PurgaAdjuntoIAPendiente(models.Model):
    attachment_id = models.UUIDField(unique=True)
    storage_name = models.CharField(max_length=255)
    error_code = models.CharField(max_length=64, default="storage_delete_failed")
    attempts = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Purga pendiente de adjunto INTASA IA"
        verbose_name_plural = "Purgas pendientes de adjuntos INTASA IA"
