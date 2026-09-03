"""
PORTAL INTASA · Memoria de compra V1.

Mantiene el último precio y unidad por artículo/proveedor y
proporciona sugerencias para nuevas líneas.

No convierte unidades técnicas, de compra o de uso.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .unit_catalog_v1 import (
    normalize_nature,
    normalize_unit,
)


SOURCE_PRIORITY = {
    "CATALOGO": 5,
    "ALIAS": 10,
    "ALBARAN": 20,
    "FACTURA": 30,
}


def _decimal(value):
    try:
        return Decimal(
            str(value)
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return Decimal("0")


def _positive(value):
    return _decimal(value) > 0


def _as_date(value):
    if isinstance(
        value,
        datetime,
    ):
        return value.date()

    if isinstance(
        value,
        date,
    ):
        return value

    if value:
        try:
            return date.fromisoformat(
                str(value)[:10]
            )
        except ValueError:
            return None

    return None


def _date_rank(value):
    parsed = _as_date(value)

    if parsed is None:
        return 0

    return parsed.toordinal()


def _provider_name(provider):
    if provider is None:
        return ""

    return str(
        getattr(
            provider,
            "nombre_comercial",
            "",
        )
        or provider
    )


def _candidate(
    *,
    price,
    unit,
    purchase_date,
    provider,
    source,
    document_code="",
    document_number="",
    object_id=0,
):
    if not _positive(price):
        return None

    return {
        "precio": _decimal(price),
        "unidad_compra": normalize_unit(
            unit
        ),
        "fecha": _as_date(
            purchase_date
        ),
        "proveedor_id": getattr(
            provider,
            "pk",
            None,
        ),
        "proveedor": _provider_name(
            provider
        ),
        "fuente": source,
        "prioridad": SOURCE_PRIORITY.get(
            source,
            0,
        ),
        "documento_codigo": str(
            document_code or ""
        ),
        "documento_numero": str(
            document_number or ""
        ),
        "objeto_id": int(
            object_id or 0
        ),
    }


def _candidate_sort_key(
    candidate,
    requested_provider_id,
):
    same_provider = int(
        bool(
            requested_provider_id
            and candidate.get(
                "proveedor_id"
            )
            == requested_provider_id
        )
    )

    return (
        same_provider,
        _date_rank(
            candidate.get("fecha")
        ),
        int(
            candidate.get(
                "prioridad"
            )
            or 0
        ),
        int(
            candidate.get(
                "objeto_id"
            )
            or 0
        ),
    )


def _alias_candidate(alias):
    raw = dict(
        alias.raw_data
        if isinstance(
            alias.raw_data,
            dict,
        )
        else {}
    )

    source = str(
        raw.get(
            "memoria_fuente"
        )
        or "ALIAS"
    ).upper()

    if source not in SOURCE_PRIORITY:
        source = "ALIAS"

    return _candidate(
        price=alias.ultimo_precio,
        unit=alias.unidad_proveedor,
        purchase_date=alias.ultima_fecha,
        provider=alias.proveedor,
        source=source,
        document_code=raw.get(
            "documento_codigo"
        ),
        document_number=raw.get(
            "documento_numero"
        ),
        object_id=alias.pk,
    )


def _invoice_candidate(line):
    invoice = line.factura

    return _candidate(
        price=line.precio_unitario,
        unit=line.unidad_compra,
        purchase_date=invoice.fecha_emision,
        provider=invoice.proveedor,
        source="FACTURA",
        document_code=invoice.cod_factura,
        document_number=(
            invoice.num_factura_proveedor
        ),
        object_id=line.pk,
    )


def _delivery_note_candidate(line):
    delivery_note = line.albaran

    return _candidate(
        price=line.precio_unitario,
        unit=(
            line.unidad_compra
            or line.unidad
        ),
        purchase_date=(
            delivery_note.fecha_albaran
            or delivery_note
            .fecha_entrega_mercaderia
        ),
        provider=delivery_note.proveedor,
        source="ALBARAN",
        document_code=(
            delivery_note.cod_albaran
        ),
        document_number=(
            delivery_note
            .num_albaran_proveedor
        ),
        object_id=line.pk,
    )


def purchase_suggestion(
    *,
    article,
    provider=None,
):
    """
    Recupera la mejor referencia de compra conocida.

    Se prioriza el proveedor solicitado. Dentro de ese ámbito se
    usa la referencia más reciente; a igualdad de fecha, factura
    prevalece sobre albarán.
    """

    from .models import (
        ArticuloProveedorAlias,
        FacturaProveedorLineaGestion,
        AlbaranProveedorLineaGestion,
    )

    requested_provider_id = getattr(
        provider,
        "pk",
        provider,
    )

    candidates = []

    alias_qs = (
        ArticuloProveedorAlias.objects
        .filter(
            articulo=article,
            ultimo_precio__gt=0,
        )
        .select_related(
            "proveedor",
        )
        .order_by(
            "-ultima_fecha",
            "-actualizado_en",
            "-id",
        )[:40]
    )

    for alias in alias_qs:
        candidate = _alias_candidate(
            alias
        )

        if candidate:
            candidates.append(
                candidate
            )

    invoice_qs = (
        FacturaProveedorLineaGestion.objects
        .filter(
            articulo_compra=article,
            cantidad__gt=0,
            precio_unitario__gt=0,
            importe_linea__gt=0,
        )
        .select_related(
            "factura",
            "factura__proveedor",
        )
        .order_by(
            "-factura__fecha_emision",
            "-id",
        )[:40]
    )

    for line in invoice_qs:
        candidate = _invoice_candidate(
            line
        )

        if candidate:
            candidates.append(
                candidate
            )

    delivery_note_qs = (
        AlbaranProveedorLineaGestion.objects
        .filter(
            articulo_compra=article,
            cantidad__gt=0,
            precio_unitario__gt=0,
            importe_linea__gt=0,
        )
        .select_related(
            "albaran",
            "albaran__proveedor",
        )
        .order_by(
            "-albaran__fecha_albaran",
            "-id",
        )[:40]
    )

    for line in delivery_note_qs:
        candidate = (
            _delivery_note_candidate(
                line
            )
        )

        if candidate:
            candidates.append(
                candidate
            )

    if candidates:
        selected = max(
            candidates,
            key=lambda candidate: (
                _candidate_sort_key(
                    candidate,
                    requested_provider_id,
                )
            ),
        )
    else:
        selected = None

    raw = dict(
        article.raw_data
        if isinstance(
            article.raw_data,
            dict,
        )
        else {}
    )

    habitual_unit = normalize_unit(
        raw.get(
            "unidad_compra_habitual_v1"
        )
        or article.unidad
    )

    if selected is None:
        return {
            "precio": None,
            "unidad_compra": habitual_unit,
            "fecha": None,
            "proveedor_id": None,
            "proveedor": "",
            "fuente": "CATALOGO",
            "documento_codigo": "",
            "documento_numero": "",
            "mismo_proveedor": False,
        }

    if not selected.get(
        "unidad_compra"
    ):
        selected[
            "unidad_compra"
        ] = habitual_unit

    selected[
        "mismo_proveedor"
    ] = bool(
        requested_provider_id
        and selected.get(
            "proveedor_id"
        )
        == requested_provider_id
    )

    return selected


def _should_replace(
    *,
    existing_date,
    existing_priority,
    new_date,
    new_priority,
):
    existing_date_rank = _date_rank(
        existing_date
    )

    new_date_rank = _date_rank(
        new_date
    )

    if new_date_rank > existing_date_rank:
        return True

    if new_date_rank < existing_date_rank:
        return False

    return int(
        new_priority or 0
    ) >= int(
        existing_priority or 0
    )


def _line_document_data(line):
    model_name = (
        line.__class__.__name__
    )

    if (
        model_name
        == "FacturaProveedorLineaGestion"
    ):
        document = line.factura

        return {
            "source": "FACTURA",
            "priority": (
                SOURCE_PRIORITY["FACTURA"]
            ),
            "document": document,
            "provider": document.proveedor,
            "team": document.team,
            "date": document.fecha_emision,
            "code": document.cod_factura,
            "number": (
                document
                .num_factura_proveedor
            ),
            "unit": line.unidad_compra,
        }

    document = line.albaran

    return {
        "source": "ALBARAN",
        "priority": (
            SOURCE_PRIORITY["ALBARAN"]
        ),
        "document": document,
        "provider": document.proveedor,
        "team": document.team,
        "date": (
            document.fecha_albaran
            or document
            .fecha_entrega_mercaderia
        ),
        "code": document.cod_albaran,
        "number": (
            document
            .num_albaran_proveedor
        ),
        "unit": (
            line.unidad_compra
            or line.unidad
        ),
    }


def remember_purchase_from_line(
    line,
):
    """
    Actualiza memoria de compra para una línea guardada.

    Solo actúa cuando existe artículo, proveedor y precio positivo.
    """

    from .models import (
        ArticuloProveedorAlias,
    )

    article = getattr(
        line,
        "articulo_compra",
        None,
    )

    if article is None:
        return {
            "updated": False,
            "reason": "sin_articulo",
        }

    if (
        not _positive(
            line.precio_unitario
        )
        or _decimal(
            getattr(
                line,
                "cantidad",
                0,
            )
        ) <= 0
        or _decimal(
            getattr(
                line,
                "importe_linea",
                0,
            )
        ) <= 0
    ):
        return {
            "updated": False,
            "reason": (
                "linea_no_positiva_o_sin_precio"
            ),
        }

    data = _line_document_data(
        line
    )

    provider = data["provider"]

    if provider is None:
        return {
            "updated": False,
            "reason": "sin_proveedor",
        }

    canonical_unit = normalize_unit(
        data["unit"]
    )

    # Normalizar únicamente la línea recién creada o editada.
    line_updates = {}

    if hasattr(
        line,
        "unidad_compra",
    ):
        current_purchase_unit = str(
            getattr(
                line,
                "unidad_compra",
                "",
            )
            or ""
        )

        if (
            canonical_unit
            and current_purchase_unit
            != canonical_unit
        ):
            line_updates[
                "unidad_compra"
            ] = canonical_unit

    if (
        hasattr(
            line,
            "unidad",
        )
        and getattr(
            line,
            "unidad",
            "",
        )
    ):
        current_use_unit = str(
            line.unidad or ""
        )

        normalized_use_unit = normalize_unit(
            current_use_unit
        )

        if (
            normalized_use_unit
            and current_use_unit
            != normalized_use_unit
        ):
            line_updates[
                "unidad"
            ] = normalized_use_unit

    line_raw = dict(
        line.raw_data
        if isinstance(
            line.raw_data,
            dict,
        )
        else {}
    )

    line_raw[
        "unidad_compra_v1a"
    ] = {
        "normalizada": canonical_unit,
        "source": data["source"],
        "updated_at": (
            timezone.now().isoformat()
        ),
    }

    line_updates[
        "raw_data"
    ] = line_raw

    line.__class__.objects.filter(
        pk=line.pk
    ).update(
        **line_updates
    )

    # ArticuloCompra conserva su unidad de uso existente.
    # Solo se rellena si estaba vacía.
    article_raw = dict(
        article.raw_data
        if isinstance(
            article.raw_data,
            dict,
        )
        else {}
    )

    existing_memory = dict(
        article_raw.get(
            "compra_memoria_v1"
        )
        or {}
    )

    replace_article_memory = (
        _should_replace(
            existing_date=(
                existing_memory.get(
                    "fecha"
                )
            ),
            existing_priority=(
                existing_memory.get(
                    "prioridad"
                )
            ),
            new_date=data["date"],
            new_priority=data[
                "priority"
            ],
        )
    )

    article_updates = []

    if (
        canonical_unit
        and not article.unidad
    ):
        article.unidad = canonical_unit
        article_updates.append(
            "unidad"
        )

    if canonical_unit:
        article_raw[
            "unidad_compra_habitual_v1"
        ] = canonical_unit

    if replace_article_memory:
        article_raw[
            "compra_memoria_v1"
        ] = {
            "precio": str(
                line.precio_unitario
            ),
            "unidad_compra": (
                canonical_unit
            ),
            "proveedor_id": (
                provider.pk
            ),
            "proveedor": (
                _provider_name(
                    provider
                )
            ),
            "fecha": (
                data["date"].isoformat()
                if data["date"]
                else ""
            ),
            "fuente": data["source"],
            "prioridad": (
                data["priority"]
            ),
            "documento_codigo": (
                data["code"]
            ),
            "documento_numero": (
                data["number"]
            ),
            "linea_id": line.pk,
            "updated_at": (
                timezone.now().isoformat()
            ),
        }

    article.raw_data = article_raw
    article_updates.append(
        "raw_data"
    )

    if article.tipo:
        canonical_nature = (
            normalize_nature(
                article.tipo,
                default=article.tipo,
            )
        )

        if (
            article.tipo
            in {
                "MATERIAL",
                "SERVICIO",
                "material",
                "servicio",
            }
            and article.tipo
            != canonical_nature
        ):
            article.tipo = canonical_nature
            article_updates.append(
                "tipo"
            )

    article.save(
        update_fields=list(
            dict.fromkeys(
                article_updates
                + ["actualizado_en"]
            )
        )
    )

    aliases = (
        ArticuloProveedorAlias.objects
        .filter(
            team=data["team"],
            proveedor=provider,
            articulo=article,
        )
        .order_by(
            "-ultima_fecha",
            "-actualizado_en",
            "-id",
        )
    )

    alias = aliases.first()

    if alias is None:
        alias = (
            ArticuloProveedorAlias.objects
            .create(
                team=data["team"],
                proveedor=provider,
                articulo=article,
                codigo_proveedor=(
                    f"MANUAL-A{article.pk}"
                ),
                descripcion_proveedor=(
                    article.nombre
                ),
                unidad_proveedor=(
                    canonical_unit
                ),
                ultimo_precio=None,
                ultima_fecha=None,
                estado="VINCULADO",
                raw_data={
                    "source": (
                        "purchase_memory_v1"
                    ),
                    "synthetic_code": True,
                },
            )
        )

    alias_raw = dict(
        alias.raw_data
        if isinstance(
            alias.raw_data,
            dict,
        )
        else {}
    )

    existing_priority = int(
        alias_raw.get(
            "memoria_prioridad"
        )
        or SOURCE_PRIORITY["ALIAS"]
    )

    replace_alias_memory = (
        _should_replace(
            existing_date=(
                alias.ultima_fecha
            ),
            existing_priority=(
                existing_priority
            ),
            new_date=data["date"],
            new_priority=data[
                "priority"
            ],
        )
    )

    alias.descripcion_proveedor = (
        alias.descripcion_proveedor
        or article.nombre
    )

    if canonical_unit:
        alias.unidad_proveedor = (
            canonical_unit
        )

    if replace_alias_memory:
        alias.ultimo_precio = (
            line.precio_unitario
        )

        alias.ultima_fecha = (
            data["date"]
            or timezone.localdate()
        )

        alias_raw.update(
            {
                "memoria_fuente": (
                    data["source"]
                ),
                "memoria_prioridad": (
                    data["priority"]
                ),
                "documento_codigo": (
                    data["code"]
                ),
                "documento_numero": (
                    data["number"]
                ),
                "linea_id": line.pk,
                "updated_at": (
                    timezone.now()
                    .isoformat()
                ),
            }
        )

    alias.raw_data = alias_raw

    alias.save(
        update_fields=[
            "descripcion_proveedor",
            "unidad_proveedor",
            "ultimo_precio",
            "ultima_fecha",
            "raw_data",
            "actualizado_en",
        ]
    )

    return {
        "updated": True,
        "article_id": article.pk,
        "alias_id": alias.pk,
        "unit": canonical_unit,
        "price": str(
            line.precio_unitario
        ),
        "source": data["source"],
    }
