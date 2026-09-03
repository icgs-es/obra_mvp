"""Orquestación auditable del preview V3 de documentos de comparativa."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import uuid

from django.db import transaction
from django.http import Http404
from django.utils import timezone

from intasa_ia.document_processing import (
    EXTRACTOR_VERSION,
    MAX_EXTRACTED_CHARS,
    DocumentProcessingError,
    extract_attachment,
)

from .document_intelligence import (
    BUDGET_DOCUMENT_SCHEMA_NAME,
    BUDGET_DOCUMENT_SCHEMA_VERSION,
    BudgetDocumentIntelligenceError,
    analyze_budget_document,
    build_budget_document_instructions,
)
from .models import DocumentoComparativa


DOCUMENT_INTELLIGENCE_NAMESPACE = "document_intelligence_v3"
DOCUMENT_PROCESSOR_VERSION = "comparativas-document-intelligence-slice2-v1"
MAX_ATTEMPT_HISTORY = 8


class BudgetDocumentProcessingError(RuntimeError):
    """Fallo seguro durante la orquestación del preview V3."""

    def __init__(self, code):
        self.code = str(code or "processing_failed")[:80]
        super().__init__(self.code)


@dataclass(frozen=True)
class DocumentTextResult:
    text: str
    method: str
    pages: int | None
    sheets: int | None
    ocr_used: bool
    truncated: bool
    extractor_version: str


@dataclass(frozen=True)
class _AttachmentAdapter:
    file: object
    extension: str


def _now_iso():
    return timezone.now().isoformat()


def _scope_team_ids(team_scope):
    if hasattr(team_scope, "values_list"):
        return list(team_scope.values_list("pk", flat=True))
    return [getattr(team, "pk", team) for team in team_scope]


def _document_queryset(*, team_scope, for_update=False):
    queryset = (
        DocumentoComparativa.objects
        .select_related(
            "oferta",
            "oferta__ofertante",
            "oferta__ofertante__comparativa",
            "oferta__ofertante__comparativa__team",
        )
        .filter(
            oferta__ofertante__comparativa__team_id__in=(
                _scope_team_ids(team_scope)
            )
        )
    )
    if for_update:
        queryset = queryset.select_for_update()
    return queryset


def get_scoped_budget_document(*, document_id, team_scope, for_update=False):
    try:
        return _document_queryset(
            team_scope=team_scope,
            for_update=for_update,
        ).get(pk=document_id)
    except DocumentoComparativa.DoesNotExist as exc:
        raise Http404 from exc


def _sha256_file(document):
    if not document.archivo:
        raise BudgetDocumentProcessingError("document_file_missing")
    digest = hashlib.sha256()
    try:
        document.archivo.open("rb")
        for chunk in document.archivo.chunks():
            digest.update(chunk)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise BudgetDocumentProcessingError("document_file_unavailable") from exc
    finally:
        try:
            document.archivo.close()
        except Exception:
            pass
    return digest.hexdigest()


def calculate_document_sha256(document):
    """Huella física canónica; no expone ruta ni contenido."""
    return _sha256_file(document)


def _stored_text_method(document):
    data = document.datos_extraidos or {}
    basic = data.get("importacion_basica_presupuesto") or {}
    current = data.get(DOCUMENT_INTELLIGENCE_NAMESPACE) or {}
    current_source = current.get("source") or {}
    return (
        current_source.get("text_method")
        or basic.get("method")
        or "stored_text"
    )


def extract_budget_document_text(document):
    existing = str(document.texto_extraido or "")
    if existing.strip():
        return DocumentTextResult(
            text=existing,
            method=_stored_text_method(document),
            pages=None,
            sheets=None,
            ocr_used=False,
            truncated=len(existing) > MAX_EXTRACTED_CHARS,
            extractor_version=EXTRACTOR_VERSION,
        )

    extension = str(document.extension or Path(document.nombre_original).suffix).lower()
    # El extractor neutral admite cualquier imagen que Pillow pueda verificar.
    routed_extension = ".png" if extension in {".tif", ".tiff"} else extension
    try:
        result = extract_attachment(
            _AttachmentAdapter(file=document.archivo, extension=routed_extension)
        )
    except DocumentProcessingError as exc:
        raise BudgetDocumentProcessingError(exc.code) from exc
    except (AttributeError, NotImplementedError, ValueError) as exc:
        raise BudgetDocumentProcessingError("extractor_storage_unsupported") from exc

    text = str(result.text or "").strip()
    if not text:
        raise BudgetDocumentProcessingError("extracted_text_empty")
    return DocumentTextResult(
        text=text,
        method=str(result.method or "unknown"),
        pages=result.page_count,
        sheets=result.sheet_count,
        ocr_used=bool(result.ocr_used),
        truncated=len(text) >= MAX_EXTRACTED_CHARS,
        extractor_version=EXTRACTOR_VERSION,
    )


def build_processing_fingerprint(*, document_sha256):
    instructions_sha = hashlib.sha256(
        build_budget_document_instructions().encode("utf-8")
    ).hexdigest()
    payload = {
        "document_sha256": str(document_sha256 or "").lower(),
        "schema_name": BUDGET_DOCUMENT_SCHEMA_NAME,
        "schema_version": BUDGET_DOCUMENT_SCHEMA_VERSION,
        "processor_version": DOCUMENT_PROCESSOR_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "instructions_sha256": instructions_sha,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _compact_attempt(namespace):
    if not namespace:
        return None
    request = namespace.get("request") or {}
    metadata = namespace.get("metadata") or {}
    preview = namespace.get("preview") or {}
    confirmation = namespace.get("confirmation") or {}
    return {
        "fingerprint": namespace.get("fingerprint"),
        "status": namespace.get("status"),
        "requested_at": request.get("requested_at"),
        "requested_by_user_id": request.get("requested_by_user_id"),
        "completed_at": namespace.get("completed_at"),
        "error": namespace.get("error"),
        "model": metadata.get("modelo"),
        "request_id": metadata.get("request_id"),
        "partidas_count": len(preview.get("partidas") or []),
        "review_status": namespace.get("review_status"),
        "confirmation_fingerprint": confirmation.get("fingerprint"),
        "confirmed_at": confirmation.get("confirmed_at"),
        "confirmed_by_user_id": confirmation.get("confirmed_by_user_id"),
    }


def _history_for_new_attempt(current):
    history = list((current or {}).get("history") or [])
    compact = _compact_attempt(current)
    if compact and compact.get("status") not in (None, "PROCESANDO"):
        history.append(compact)
    return history[-MAX_ATTEMPT_HISTORY:]


def _request_payload(*, user, team, action):
    return {
        "requested_at": _now_iso(),
        "requested_by_user_id": getattr(user, "pk", None),
        "team_id": team.pk,
        "action": action,
    }


def _safe_error(exc):
    if isinstance(exc, (BudgetDocumentProcessingError, BudgetDocumentIntelligenceError)):
        return str(exc)[:80]
    return "processing_failed"


def _persist_error(*, document_id, team_scope, token, error_code):
    with transaction.atomic():
        document = get_scoped_budget_document(
            document_id=document_id,
            team_scope=team_scope,
            for_update=True,
        )
        data = deepcopy(document.datos_extraidos or {})
        current = deepcopy(data.get(DOCUMENT_INTELLIGENCE_NAMESPACE) or {})
        if current.get("processing_token") != token:
            return
        current.update({
            "status": "ERROR",
            "completed_at": _now_iso(),
            "error": error_code,
        })
        current.pop("processing_token", None)
        data[DOCUMENT_INTELLIGENCE_NAMESPACE] = current
        document.datos_extraidos = data
        document.estado_analisis = DocumentoComparativa.EstadoAnalisis.ERROR
        document.error_analisis = f"Análisis INTASA IA V3 no completado ({error_code})."
        document.save(update_fields=("datos_extraidos", "estado_analisis", "error_analisis"))


def procesar_documento_presupuesto(
    document_id,
    *,
    user,
    team_scope,
    requester=None,
    extractor=None,
    force=False,
):
    """Procesa y persiste solo el preview técnico V3 del documento."""
    extractor = extractor or extract_budget_document_text
    token = uuid.uuid4().hex

    with transaction.atomic():
        document = get_scoped_budget_document(
            document_id=document_id,
            team_scope=team_scope,
            for_update=True,
        )
        team = document.oferta.ofertante.comparativa.team
        file_sha = _sha256_file(document)
        if not document.sha256 or file_sha.lower() != document.sha256.lower():
            raise BudgetDocumentProcessingError("document_sha256_mismatch")
        fingerprint = build_processing_fingerprint(document_sha256=file_sha)
        data = deepcopy(document.datos_extraidos or {})
        current = deepcopy(data.get(DOCUMENT_INTELLIGENCE_NAMESPACE) or {})

        if (
            not force
            and current.get("status") == "COMPLETADO"
            and current.get("fingerprint") == fingerprint
        ):
            return {
                "document": document,
                "namespace": current,
                "status": "COMPLETADO",
                "reused": True,
            }
        if current.get("status") == "PROCESANDO":
            return {
                "document": document,
                "namespace": current,
                "status": "PROCESANDO",
                "reused": True,
            }

        processing = {
            "schema_name": BUDGET_DOCUMENT_SCHEMA_NAME,
            "schema_version": BUDGET_DOCUMENT_SCHEMA_VERSION,
            "processor_version": DOCUMENT_PROCESSOR_VERSION,
            "fingerprint": fingerprint,
            "status": "PROCESANDO",
            "source": {
                "document_id": document.pk,
                "sha256": file_sha,
                "extractor_version": EXTRACTOR_VERSION,
            },
            "request": _request_payload(
                user=user,
                team=team,
                action="reanalyze" if force else "analyze",
            ),
            "data_ia": {},
            "preview": {},
            "validation": {},
            "metadata": {},
            "completed_at": None,
            "error": None,
            "history": _history_for_new_attempt(current),
            "processing_token": token,
        }
        data[DOCUMENT_INTELLIGENCE_NAMESPACE] = processing
        document.datos_extraidos = data
        document.estado_analisis = DocumentoComparativa.EstadoAnalisis.PROCESANDO
        document.error_analisis = ""
        document.save(update_fields=("datos_extraidos", "estado_analisis", "error_analisis"))

    try:
        document = get_scoped_budget_document(
            document_id=document_id,
            team_scope=team_scope,
        )
        extraction = extractor(document)
        if not isinstance(extraction, DocumentTextResult):
            raise BudgetDocumentProcessingError("extractor_result_invalid")

        if not document.texto_extraido.strip():
            with transaction.atomic():
                locked = get_scoped_budget_document(
                    document_id=document_id,
                    team_scope=team_scope,
                    for_update=True,
                )
                current = (locked.datos_extraidos or {}).get(
                    DOCUMENT_INTELLIGENCE_NAMESPACE
                ) or {}
                if current.get("processing_token") != token:
                    raise BudgetDocumentProcessingError("processing_superseded")
                locked.texto_extraido = extraction.text
                locked.save(update_fields=("texto_extraido",))

        document = get_scoped_budget_document(
            document_id=document_id,
            team_scope=team_scope,
        )
        team = document.oferta.ofertante.comparativa.team
        result = analyze_budget_document(
            document=document,
            user=user,
            team=team,
            requester=requester,
        )

        with transaction.atomic():
            document = get_scoped_budget_document(
                document_id=document_id,
                team_scope=team_scope,
                for_update=True,
            )
            data = deepcopy(document.datos_extraidos or {})
            current = deepcopy(data.get(DOCUMENT_INTELLIGENCE_NAMESPACE) or {})
            if current.get("processing_token") != token:
                raise BudgetDocumentProcessingError("processing_superseded")
            current.update({
                "status": "COMPLETADO",
                "source": {
                    "document_id": document.pk,
                    "sha256": document.sha256,
                    "text_method": extraction.method,
                    "text_len": len(extraction.text),
                    "pages": extraction.pages,
                    "sheets": extraction.sheets,
                    "ocr_used": extraction.ocr_used,
                    "truncated": bool(
                        extraction.truncated
                        or result["source"].get("text_truncated")
                    ),
                    "extractor_version": extraction.extractor_version,
                },
                "data_ia": result["data_ia"],
                "preview": result["preview"],
                "validation": result["validation"],
                "metadata": result["provider"],
                "completed_at": _now_iso(),
                "error": None,
            })
            current.pop("processing_token", None)
            data[DOCUMENT_INTELLIGENCE_NAMESPACE] = current
            document.datos_extraidos = data
            document.estado_analisis = DocumentoComparativa.EstadoAnalisis.COMPLETADO
            document.error_analisis = ""
            document.save(update_fields=("datos_extraidos", "estado_analisis", "error_analisis"))

        return {
            "document": document,
            "namespace": current,
            "status": "COMPLETADO",
            "reused": False,
        }
    except Exception as exc:
        error_code = _safe_error(exc)
        _persist_error(
            document_id=document_id,
            team_scope=team_scope,
            token=token,
            error_code=error_code,
        )
        if isinstance(exc, Http404):
            raise
        raise BudgetDocumentProcessingError(error_code) from exc
