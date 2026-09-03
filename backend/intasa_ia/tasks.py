import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .document_processing import (
    EXTRACTOR_VERSION,
    MAX_EXTRACTED_CHARS,
    DocumentProcessingError,
    extract_attachment,
)
from .invoice_role_analysis import analyze_invoice_text
from .invoice_response_guard import enforce_invoice_role_safety
from .help_bridge import generar_respuesta_segura
from .models import AdjuntoIA, MensajeIA, ProcesamientoMensajeIA
from .provider_openai import IAProviderError
from .services import build_document_context


logger = logging.getLogger(__name__)
MAX_MESSAGE_EXTRACTED_CHARS = 250_000


def _safe_provider_error(code):
    if code == "timeout":
        return "El documento se procesó, pero la respuesta de INTASA IA agotó el tiempo disponible."
    return "El documento se procesó, pero no fue posible generar la respuesta de INTASA IA."


@shared_task(bind=True, soft_time_limit=270, time_limit=300, max_retries=0)
def process_document_message(self, processing_id, task_key):
    try:
        with transaction.atomic():
            processing = (
                ProcesamientoMensajeIA.objects.select_for_update()
                .select_related("message__conversacion__user")
                .get(pk=processing_id, task_key=task_key)
            )
            if processing.status in {
                ProcesamientoMensajeIA.Estado.PROCESSING,
                ProcesamientoMensajeIA.Estado.GENERATING,
                ProcesamientoMensajeIA.Estado.COMPLETED,
            }:
                return processing.status
            processing.status = ProcesamientoMensajeIA.Estado.PROCESSING
            processing.started_at = timezone.now()
            processing.attempts += 1
            processing.error_code = ""
            processing.save(update_fields=(
                "status", "started_at", "attempts", "error_code", "updated_at"
            ))
            message_id = processing.message_id

        attachments = list(AdjuntoIA.objects.filter(message_id=message_id).order_by("created_at", "id"))
        remaining = MAX_MESSAGE_EXTRACTED_CHARS
        for attachment in attachments:
            if (
                attachment.status == AdjuntoIA.Estado.READY
                and attachment.processed_source_sha256 == attachment.sha256
                and attachment.extracted_text
                and (attachment.extension.lower() != ".pdf" or attachment.invoice_analysis)
            ):
                remaining = max(0, remaining - len(attachment.extracted_text))
                continue
            attachment.status = AdjuntoIA.Estado.PROCESSING
            attachment.processing_started_at = timezone.now()
            attachment.error_code = ""
            attachment.save(update_fields=("status", "processing_started_at", "error_code"))
            try:
                result = extract_attachment(attachment)
                text = result.text[:min(MAX_EXTRACTED_CHARS, remaining)]
                remaining = max(0, remaining - len(text))
                if not text:
                    raise DocumentProcessingError("empty_extraction")
                attachment.status = AdjuntoIA.Estado.READY
                attachment.extracted_text = text
                attachment.invoice_analysis = (
                    analyze_invoice_text(text)
                    if attachment.extension.lower() == ".pdf" else {}
                )
                attachment.processing_method = result.method
                attachment.technical_summary = result.summary[:500]
                attachment.page_count = result.page_count
                attachment.sheet_count = result.sheet_count
                attachment.ocr_used = result.ocr_used
                attachment.extractor_version = EXTRACTOR_VERSION
                attachment.processed_source_sha256 = attachment.sha256
                attachment.processed_at = timezone.now()
            except DocumentProcessingError as exc:
                attachment.status = AdjuntoIA.Estado.FAILED
                attachment.error_code = exc.code[:64]
                attachment.extracted_text = ""
                attachment.invoice_analysis = {}
                attachment.processed_at = timezone.now()
            except Exception:
                logger.error("INTASA IA document extraction failed attachment=%s", attachment.pk)
                attachment.status = AdjuntoIA.Estado.FAILED
                attachment.error_code = "unexpected_extractor_error"
                attachment.extracted_text = ""
                attachment.invoice_analysis = {}
                attachment.processed_at = timezone.now()
            attachment.save()

        with transaction.atomic():
            processing = ProcesamientoMensajeIA.objects.select_for_update().select_related(
                "message__conversacion__user"
            ).get(pk=processing_id)
            if processing.assistant_message_id:
                processing.status = ProcesamientoMensajeIA.Estado.COMPLETED
                processing.completed_at = timezone.now()
                processing.save(update_fields=("status", "completed_at", "updated_at"))
                return processing.status
            processing.status = ProcesamientoMensajeIA.Estado.GENERATING
            processing.save(update_fields=("status", "updated_at"))
            message = processing.message
            conversation = message.conversacion

        attachments = list(AdjuntoIA.objects.filter(message=message).order_by("created_at", "id"))
        ready = [item for item in attachments if item.status == AdjuntoIA.Estado.READY]
        failed = [item for item in attachments if item.status == AdjuntoIA.Estado.FAILED]
        if not ready:
            result = {
                "contenido": "No se pudo procesar ningún archivo adjunto. Revisa su estado y vuelve a intentarlo.",
                "proveedor": "local-document-processing",
                "modelo": EXTRACTOR_VERSION,
                "request_id": "", "tokens_entrada": None, "tokens_salida": None,
                "metadata": {"external_call": False, "store": False, "document_processing": True},
            }
        else:
            question = message.contenido.strip() or "Analiza los archivos adjuntos y resume la información relevante."
            try:
                result = generar_respuesta_segura(
                    pregunta=question,
                    user=conversation.user,
                    team=None,
                    conversacion=conversation,
                    document_context=build_document_context(ready),
                    has_documents=True,
                    web_search_enabled=False,
                )
            except IAProviderError as exc:
                result = {
                    "contenido": _safe_provider_error(exc.code),
                    "proveedor": "openai-error", "modelo": "", "request_id": exc.request_id,
                    "tokens_entrada": None, "tokens_salida": None,
                    "metadata": {"external_call": True, "store": False, "error_code": exc.code,
                                 "document_processing": True, "web_search_used": False},
                }
        if failed:
            names = ", ".join(item.safe_display_name for item in failed)
            result = dict(result)
            result["contenido"] = str(result["contenido"]).rstrip() + f"\n\nNo se pudo procesar: {names}."

        result = dict(result)
        result["contenido"] = enforce_invoice_role_safety(
            result["contenido"], [item.invoice_analysis for item in ready if item.invoice_analysis]
        )

        with transaction.atomic():
            processing = ProcesamientoMensajeIA.objects.select_for_update().get(pk=processing_id)
            if not processing.assistant_message_id:
                assistant = MensajeIA.objects.create(
                    conversacion_id=message.conversacion_id,
                    rol=MensajeIA.Rol.ASISTENTE,
                    contenido=result["contenido"], proveedor=result["proveedor"],
                    modelo=result["modelo"], request_id=result["request_id"],
                    tokens_entrada=result["tokens_entrada"], tokens_salida=result["tokens_salida"],
                    metadata={**result["metadata"], "generation_key": str(processing.generation_key),
                              "attachment_ids": [str(item.pk) for item in ready],
                              "web_search_used": False, "files_api_used": False, "direct_pdf_used": False},
                )
                processing.assistant_message = assistant
            processing.status = ProcesamientoMensajeIA.Estado.COMPLETED
            processing.completed_at = timezone.now()
            processing.save(update_fields=("assistant_message", "status", "completed_at", "updated_at"))
            processing.message.conversacion.save(update_fields=("updated_at",))
        return ProcesamientoMensajeIA.Estado.COMPLETED
    except ProcesamientoMensajeIA.DoesNotExist:
        return "missing"
    except Exception:
        logger.error("INTASA IA document message task failed processing=%s", processing_id)
        ProcesamientoMensajeIA.objects.filter(pk=processing_id).update(
            status=ProcesamientoMensajeIA.Estado.FAILED,
            error_code="task_failed",
            completed_at=timezone.now(),
        )
        AdjuntoIA.objects.filter(
            message__document_processing__id=processing_id,
            status=AdjuntoIA.Estado.PROCESSING,
        ).update(status=AdjuntoIA.Estado.FAILED, error_code="task_failed", processed_at=timezone.now())
        return "failed"
