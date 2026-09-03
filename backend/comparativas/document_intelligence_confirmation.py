"""Confirmación humana y atómica de una preview V3."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal
import hashlib
import json
import re
import unicodedata

from django.db import transaction
from django.utils import timezone

from .concept_extraction import reconcile_concepts
from .document_intelligence_processing import (
    DOCUMENT_INTELLIGENCE_NAMESPACE,
    build_processing_fingerprint,
    calculate_document_sha256,
    get_scoped_budget_document,
)
from .integrations import resolve_proveedor_for_team
from .models import ConceptoOferta, DocumentoComparativa, Oferta, Ofertante, RelacionConcepto


class BudgetConfirmationError(RuntimeError):
    def __init__(self, code):
        self.code = str(code or "confirmation_failed")[:80]
        super().__init__(self.code)


def _json_safe(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _normalized(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value.lower()).strip()


def _reviewed_payload(header, rows):
    return {
        "documento": {
            "proveedor_emisor": header.get("proveedor_emisor") or "",
            "nif_cif": header.get("proveedor_nif_cif") or "",
            "numero": header.get("numero") or "",
            "fecha": header.get("fecha"),
        },
        "cliente": {
            "nombre": header.get("cliente_nombre") or "",
            "nif_cif": header.get("cliente_nif_cif") or "",
            "direccion": header.get("cliente_direccion") or "",
        },
        "economia": {
            "base": header.get("base"),
            "iva": header.get("iva"),
            "total": header.get("total"),
            "moneda": (header.get("moneda") or "").upper(),
        },
        "condiciones_comerciales": {
            "forma_pago": header.get("forma_pago") or "",
            "validez": header.get("validez") or "",
            "plazo": header.get("plazo") or "",
            "portes": header.get("portes") or "",
            "observaciones": header.get("observaciones") or "",
        },
        "partidas": [
            {
                "source_index": row["source_index"],
                "selected": bool(row.get("selected")),
                "codigo": row.get("codigo") or "",
                "descripcion": row.get("descripcion") or "",
                "cantidad": row.get("cantidad"),
                "unidad": row.get("unidad") or "",
                "precio_unitario": row.get("precio_unitario"),
                "importe": row.get("importe"),
                "alcance": row.get("alcance") or ConceptoOferta.Alcance.REVISAR,
            }
            for row in rows
        ],
    }


def _initial_payload(document):
    namespace = (document.datos_extraidos or {}).get(DOCUMENT_INTELLIGENCE_NAMESPACE) or {}
    confirmation = namespace.get("confirmation") or {}
    reviewed = confirmation.get("reviewed_data")
    if reviewed:
        return deepcopy(reviewed)
    preview = namespace.get("preview") or {}
    return {
        "documento": deepcopy(preview.get("documento") or {}),
        "cliente": deepcopy(preview.get("cliente") or {}),
        "economia": deepcopy(preview.get("economia") or {}),
        "condiciones_comerciales": deepcopy(preview.get("condiciones_comerciales") or {}),
        "partidas": [
            {"source_index": index, "selected": True, **deepcopy(item)}
            for index, item in enumerate(preview.get("partidas") or [])
        ],
    }


def build_budget_review_initial(document):
    namespace = (document.datos_extraidos or {}).get(DOCUMENT_INTELLIGENCE_NAMESPACE) or {}
    confirmation = namespace.get("confirmation") or {}
    payload = _initial_payload(document)
    document_data = payload.get("documento") or {}
    customer = payload.get("cliente") or {}
    economy = payload.get("economia") or {}
    conditions = payload.get("condiciones_comerciales") or {}
    bidder = document.oferta.ofertante
    header = {
        "preview_fingerprint": namespace.get("fingerprint") or "",
        "document_sha256": document.sha256,
        "proveedor_ref": str(confirmation.get("provider_ref_id") or ""),
        "confirmar_vinculo_proveedor": bool(confirmation.get("provider_link_confirmed")),
        "proveedor_emisor": document_data.get("proveedor_emisor") or bidder.nombre,
        "proveedor_nif_cif": document_data.get("nif_cif") or bidder.nif,
        "numero": document_data.get("numero") or "",
        "fecha": document_data.get("fecha") or None,
        "cliente_nombre": customer.get("nombre") or "",
        "cliente_nif_cif": customer.get("nif_cif") or "",
        "cliente_direccion": customer.get("direccion") or "",
        "base": economy.get("base"),
        "iva": economy.get("iva"),
        "total": economy.get("total"),
        "moneda": economy.get("moneda") or document.oferta.moneda,
        "forma_pago": conditions.get("forma_pago") or "",
        "validez": conditions.get("validez") or "",
        "plazo": conditions.get("plazo") or "",
        "portes": conditions.get("portes") or "",
        "observaciones": conditions.get("observaciones") or "",
        "aceptar_advertencias": False,
        "reemplazar_conceptos": False,
    }
    items = []
    for index, item in enumerate(payload.get("partidas") or []):
        items.append({
            "selected": item.get("selected", True),
            "source_index": item.get("source_index", index),
            "codigo": item.get("codigo") or "",
            "descripcion": item.get("descripcion") or "",
            "cantidad": item.get("cantidad"),
            "unidad": item.get("unidad") or "",
            "precio_unitario": item.get("precio_unitario"),
            "importe": item.get("importe"),
            "alcance": item.get("alcance") or ConceptoOferta.Alcance.REVISAR,
        })
    return header, items


def preview_requires_warning_acceptance(namespace):
    preview = namespace.get("preview") or {}
    validation = namespace.get("validation") or {}
    if (preview.get("revision") or {}).get("advertencias"):
        return True
    economic = validation.get("economia") or {}
    return any(
        (economic.get(key) or {}).get("status") == "REVIEW"
        for key in ("header", "items_vs_base")
    ) or any(
        (item.get("arithmetic") or {}).get("status") == "REVIEW"
        for item in validation.get("partidas") or []
    )


def _manual_changes(*, initial, reviewed):
    changes = []
    for section in ("documento", "cliente", "economia", "condiciones_comerciales"):
        before = initial.get(section) or {}
        after = reviewed.get(section) or {}
        for field in set(before) | set(after):
            if _json_safe(before.get(field)) != _json_safe(after.get(field)):
                changes.append(f"{section}.{field}")
    initial_items = {int(item["source_index"]): item for item in initial.get("partidas") or []}
    for item in reviewed.get("partidas") or []:
        index = int(item["source_index"])
        before = initial_items.get(index) or {}
        for field in ("selected", "codigo", "descripcion", "cantidad", "unidad", "precio_unitario", "importe", "alcance"):
            if _json_safe(before.get(field)) != _json_safe(item.get(field)):
                changes.append(f"partidas.{index}.{field}")
    return sorted(set(changes))


def _confirmation_fingerprint(*, preview_fingerprint, reviewed, provider_ref, confirm_provider):
    payload = {
        "preview_fingerprint": preview_fingerprint,
        "reviewed": _json_safe(reviewed),
        "provider_ref": provider_ref or None,
        "confirm_provider": bool(confirm_provider),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _reconciliation(reviewed):
    for item in reviewed.get("partidas", []):
        for key in ("cantidad", "precio_unitario", "importe"):
            value = item.get(key)
            if value not in (None, "") and not isinstance(value, Decimal):
                item[key] = Decimal(str(value))
    for key in ("base", "iva", "total"):
        value = reviewed["economia"].get(key)
        if value not in (None, "") and not isinstance(value, Decimal):
            reviewed["economia"][key] = Decimal(str(value))
    selected = [item for item in reviewed["partidas"] if item["selected"]]
    concepts = [{"alcance": item["alcance"], "importe": item["importe"]} for item in selected]
    result = reconcile_concepts(concepts, reviewed["economia"]["base"])
    base = reviewed["economia"]["base"]
    tax = reviewed["economia"]["iva"]
    total = reviewed["economia"]["total"]
    if base is None or tax is None or total is None:
        header = {"status": "NO_DISPONIBLE", "difference": None}
    else:
        difference = (base + tax) - total
        header = {
            "status": "COMPLETA" if abs(difference) <= Decimal("0.05") else "PARCIAL",
            "difference": difference,
        }
    item_arithmetic = []
    for item in selected:
        quantity, price, amount = item["cantidad"], item["precio_unitario"], item["importe"]
        if quantity is None or price is None or amount is None:
            status, difference = "NO_VERIFICABLE", None
        else:
            difference = (quantity * price) - amount
            status = "COMPLETA" if abs(difference) <= Decimal("0.02") else "PARCIAL"
        item_arithmetic.append({
            "source_index": item["source_index"],
            "status": status,
            "difference": difference,
        })
    return {"concepts_vs_base": result, "header": header, "items": item_arithmetic}


@transaction.atomic
def confirm_budget_document(
    document_id,
    *,
    user,
    team_scope,
    header,
    reviewed_rows,
    provider_resolver=resolve_proveedor_for_team,
):
    document = get_scoped_budget_document(
        document_id=document_id,
        team_scope=team_scope,
        for_update=True,
    )
    offer = Oferta.objects.select_for_update().get(pk=document.oferta_id)
    bidder = Ofertante.objects.select_for_update().get(pk=offer.ofertante_id)
    team_id = bidder.comparativa.team_id
    data = deepcopy(document.datos_extraidos or {})
    namespace = deepcopy(data.get(DOCUMENT_INTELLIGENCE_NAMESPACE) or {})
    if namespace.get("status") != "COMPLETADO":
        raise BudgetConfirmationError("preview_not_completed")
    physical_sha = calculate_document_sha256(document)
    if physical_sha != document.sha256 or str(header.get("document_sha256") or "") != document.sha256:
        raise BudgetConfirmationError("document_sha256_changed")
    expected_fingerprint = build_processing_fingerprint(document_sha256=document.sha256)
    preview_fingerprint = namespace.get("fingerprint")
    if (
        preview_fingerprint != expected_fingerprint
        or str(header.get("preview_fingerprint") or "") != preview_fingerprint
    ):
        raise BudgetConfirmationError("preview_fingerprint_stale")

    source_items = (namespace.get("preview") or {}).get("partidas") or []
    if len(reviewed_rows) != len(source_items):
        raise BudgetConfirmationError("reviewed_items_invalid")
    indices = [int(row["source_index"]) for row in reviewed_rows]
    if set(indices) != set(range(len(source_items))) or len(set(indices)) != len(indices):
        raise BudgetConfirmationError("reviewed_items_invalid")
    if not any(row.get("selected") for row in reviewed_rows):
        raise BudgetConfirmationError("reviewed_items_empty")
    if preview_requires_warning_acceptance(namespace) and not header.get("aceptar_advertencias"):
        raise BudgetConfirmationError("warnings_not_accepted")

    reviewed = _reviewed_payload(header, reviewed_rows)
    initial = _initial_payload(document)
    manual_changes = _manual_changes(initial=initial, reviewed=reviewed)
    provider_ref = header.get("proveedor_ref") or None
    confirm_provider = bool(header.get("confirmar_vinculo_proveedor"))
    if provider_ref and not confirm_provider:
        raise BudgetConfirmationError("provider_link_not_confirmed")
    if confirm_provider and not provider_ref:
        raise BudgetConfirmationError("provider_missing")
    provider = None
    if confirm_provider:
        provider = provider_resolver(team_id, provider_ref)
        if not provider:
            raise BudgetConfirmationError("provider_out_of_scope")

    confirmation_fingerprint = _confirmation_fingerprint(
        preview_fingerprint=preview_fingerprint,
        reviewed=reviewed,
        provider_ref=provider_ref,
        confirm_provider=confirm_provider,
    )
    previous_confirmation = namespace.get("confirmation") or {}
    existing = list(
        ConceptoOferta.objects.select_for_update()
        .filter(documento=document)
        .order_by("orden", "id")
    )
    if (
        previous_confirmation.get("status") == "CONFIRMED"
        and previous_confirmation.get("fingerprint") == confirmation_fingerprint
    ):
        return {
            "concepts": existing,
            "reused": True,
            "reconciliation": previous_confirmation.get("reconciliation") or {},
            "manual_changes": previous_confirmation.get("manual_changes") or [],
        }
    if existing:
        if not header.get("reemplazar_conceptos"):
            raise BudgetConfirmationError("existing_concepts_require_replace")
        if RelacionConcepto.objects.filter(
            concepto_id__in=[item.pk for item in existing]
        ).exists():
            raise BudgetConfirmationError("existing_concepts_have_relations")
        ConceptoOferta.objects.filter(pk__in=[item.pk for item in existing]).delete()

    offer.fecha_documento = reviewed["documento"]["fecha"]
    offer.referencia = reviewed["documento"]["numero"][:160]
    offer.base = reviewed["economia"]["base"]
    offer.impuestos = reviewed["economia"]["iva"]
    offer.total = reviewed["economia"]["total"]
    offer.estado = Oferta.Estado.ANALIZADA
    offer.save(update_fields=(
        "fecha_documento", "referencia", "base", "impuestos", "total", "estado", "updated_at",
    ))

    if provider:
        bidder.tipo = Ofertante.Tipo.PROVEEDOR
        bidder.proveedor_ref_id = provider["id"]
        bidder.nombre = provider["nombre"]
        bidder.nif = provider.get("nif") or ""
        bidder.email = provider.get("email") or ""
        bidder.telefono = provider.get("telefono") or ""
        bidder.save(update_fields=(
            "tipo", "proveedor_ref_id", "nombre", "nif", "email", "telefono", "updated_at",
        ))
    else:
        if {"documento.proveedor_emisor", "documento.nif_cif"}.intersection(manual_changes):
            bidder.nombre = reviewed["documento"]["proveedor_emisor"][:255]
            bidder.nif = reviewed["documento"]["nif_cif"][:60]
            bidder.save(update_fields=("nombre", "nif", "updated_at"))

    confidence = ((namespace.get("preview") or {}).get("revision") or {}).get(
        "confianza_documental"
    ) or ConceptoOferta.Confianza.REVISAR
    if confidence not in {choice[0] for choice in ConceptoOferta.Confianza.choices}:
        confidence = ConceptoOferta.Confianza.REVISAR
    changes = set(manual_changes)
    created = []
    for order, item in enumerate(
        (item for item in reviewed["partidas"] if item["selected"]),
        start=1,
    ):
        source = source_items[item["source_index"]]
        item_edited = any(key.startswith(f"partidas.{item['source_index']}.") for key in changes)
        concept = ConceptoOferta(
            oferta=offer,
            documento=document,
            orden=order,
            codigo_original=item["codigo"][:120],
            titulo_original=item["descripcion"][:500],
            descripcion_original=item["descripcion"],
            texto_normalizado=_normalized(item["descripcion"]),
            cantidad=item["cantidad"],
            unidad=item["unidad"][:40],
            precio_unitario=item["precio_unitario"],
            importe=item["importe"],
            alcance=item["alcance"],
            evidencia=str(source.get("evidencia") or ""),
            origen=(ConceptoOferta.Origen.HUMANO if item_edited else ConceptoOferta.Origen.IA),
            confianza_extraccion=confidence,
            raw_data={
                "v3": {
                    "source_index": item["source_index"],
                    "source_document_sha256": document.sha256,
                    "preview_fingerprint": preview_fingerprint,
                    "confirmation_fingerprint": confirmation_fingerprint,
                    "human_confirmed": True,
                    "human_edited": item_edited,
                    "confirmed_by_user_id": getattr(user, "pk", None),
                    "evidence": source.get("evidencia") or "",
                    "source": _json_safe(source),
                }
            },
        )
        concept.save()
        created.append(concept)

    reconciliation = _reconciliation(reviewed)
    now = timezone.now().isoformat()
    history = list(namespace.get("confirmation_history") or [])
    if previous_confirmation:
        history.append({
            key: previous_confirmation.get(key)
            for key in ("fingerprint", "confirmed_at", "confirmed_by_user_id", "concept_count")
        })
    namespace["review_status"] = "CONFIRMED"
    namespace["confirmation"] = {
        "status": "CONFIRMED",
        "fingerprint": confirmation_fingerprint,
        "preview_fingerprint": preview_fingerprint,
        "source_sha256": document.sha256,
        "schema_name": namespace.get("schema_name"),
        "schema_version": namespace.get("schema_version"),
        "confirmed_at": now,
        "confirmed_by_user_id": getattr(user, "pk", None),
        "origin": "document_intelligence_v3_human_review",
        "concept_count": len(created),
        "manual_changes": manual_changes,
        "warnings_accepted": bool(header.get("aceptar_advertencias")),
        "provider_link_confirmed": bool(provider),
        "provider_ref_id": provider["id"] if provider else bidder.proveedor_ref_id,
        "reconciliation": _json_safe(reconciliation),
        "reviewed_data": _json_safe(reviewed),
    }
    namespace["confirmation_history"] = history[-8:]
    data[DOCUMENT_INTELLIGENCE_NAMESPACE] = namespace
    document.datos_extraidos = data
    document.estado_analisis = DocumentoComparativa.EstadoAnalisis.COMPLETADO
    document.error_analisis = ""
    document.save(update_fields=("datos_extraidos", "estado_analisis", "error_analisis"))
    return {
        "concepts": created,
        "reused": False,
        "reconciliation": reconciliation,
        "manual_changes": manual_changes,
    }
