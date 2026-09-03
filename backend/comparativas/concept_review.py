"""
Persistencia de conceptos revisados por una persona.

Este servicio:
- no ejecuta OCR;
- no llama a IA;
- no interpreta documentos;
- recibe una previsualización recalculada en servidor;
- valida índices de origen;
- conserva evidencia documental;
- marca como HUMANO cualquier edición realizada;
- evita una segunda confirmación silenciosa.
"""

import re
import unicodedata

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .concept_extraction import (
    reconcile_concepts,
)
from .models import (
    ConceptoOferta,
    DocumentoComparativa,
)


class ConceptosYaConfirmados(Exception):
    pass


def _normalize_text(value):
    value = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(
            char
        )
    )

    return re.sub(
        r"\s+",
        " ",
        value.lower(),
    ).strip()


def _positive_int(value):
    try:
        value = int(value)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if value < 0:
        return None

    return value


def _json_safe(value):
    if isinstance(
        value,
        Decimal,
    ):
        return format(
            value,
            "f",
        )

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key): _json_safe(item)
            for key, item
            in value.items()
        }

    if isinstance(
        value,
        (list, tuple),
    ):
        return [
            _json_safe(item)
            for item in value
        ]

    return value


def _source_title(source):
    value = (
        source.get("titulo")
        or source.get("evidencia")
        or ""
    )

    return str(value)[:500]


def _source_alcance(source):
    value = (
        source.get("alcance")
        or ConceptoOferta.Alcance.REVISAR
    )

    allowed = {
        choice[0]
        for choice
        in ConceptoOferta.Alcance.choices
    }

    if value not in allowed:
        return (
            ConceptoOferta
            .Alcance
            .REVISAR
        )

    return value


def build_review_initial(
    preview_concepts,
):
    result = []

    for index, source in enumerate(
        preview_concepts
    ):
        result.append({
            "selected": True,
            "source_index": index,
            "titulo": _source_title(
                source
            ),
            "descripcion": (
                source.get(
                    "descripcion"
                )
                or ""
            ),
            "cantidad": source.get(
                "cantidad"
            ),
            "unidad": (
                source.get(
                    "unidad"
                )
                or ""
            ),
            "precio_unitario": (
                source.get(
                    "precio_unitario"
                )
            ),
            "importe": source.get(
                "importe"
            ),
            "alcance": (
                _source_alcance(
                    source
                )
            ),
        })

    return result


def _row_was_edited(
    source,
    reviewed,
):
    initial = build_review_initial(
        [source]
    )[0]

    keys = (
        "titulo",
        "descripcion",
        "cantidad",
        "unidad",
        "precio_unitario",
        "importe",
        "alcance",
    )

    for key in keys:
        left = initial.get(key)
        right = reviewed.get(key)

        if (
            isinstance(
                left,
                Decimal,
            )
            or isinstance(
                right,
                Decimal,
            )
        ):
            if left != right:
                return True

            continue

        if str(
            left or ""
        ).strip() != str(
            right or ""
        ).strip():
            return True

    return False


@transaction.atomic
def confirm_document_concepts(
    *,
    documento_id,
    preview,
    reviewed_rows,
    user,
):
    documento = (
        DocumentoComparativa.objects
        .select_for_update()
        .select_related(
            "oferta",
        )
        .get(
            pk=documento_id
        )
    )

    if (
        ConceptoOferta.objects
        .filter(
            documento=documento
        )
        .exists()
    ):
        raise ConceptosYaConfirmados(
            "Los conceptos de este documento "
            "ya fueron confirmados."
        )

    source_concepts = (
        preview.get(
            "conceptos"
        )
        or []
    )

    if not reviewed_rows:
        raise ValueError(
            "Debe confirmarse al menos "
            "un concepto."
        )

    valid_confidence = {
        choice[0]
        for choice
        in ConceptoOferta
        .Confianza
        .choices
    }

    valid_scope = {
        choice[0]
        for choice
        in ConceptoOferta
        .Alcance
        .choices
    }

    seen = set()
    created = []

    for order, reviewed in enumerate(
        reviewed_rows,
        start=1,
    ):
        source_index = int(
            reviewed[
                "source_index"
            ]
        )

        if (
            source_index < 0
            or source_index
            >= len(
                source_concepts
            )
            or source_index
            in seen
        ):
            raise ValueError(
                "Índice de concepto "
                "no válido."
            )

        seen.add(
            source_index
        )

        source = source_concepts[
            source_index
        ]

        human_edited = (
            _row_was_edited(
                source,
                reviewed,
            )
        )

        confidence = (
            source.get(
                "confianza"
            )
            or (
                ConceptoOferta
                .Confianza
                .REVISAR
            )
        )

        if (
            confidence
            not in valid_confidence
        ):
            confidence = (
                ConceptoOferta
                .Confianza
                .REVISAR
            )

        scope = reviewed.get(
            "alcance"
        )

        if scope not in valid_scope:
            scope = (
                ConceptoOferta
                .Alcance
                .REVISAR
            )

        title = (
            reviewed.get(
                "titulo"
            )
            or ""
        ).strip()[:500]

        description = (
            reviewed.get(
                "descripcion"
            )
            or ""
        ).strip()

        evidence = (
            source.get(
                "evidencia"
            )
            or source.get(
                "titulo"
            )
            or ""
        )

        strategy = (
            source.get(
                "strategy"
            )
            or ""
        )

        evidence_source = (
            "pdf_layout"
            if strategy
            == "PDF_LAYOUT_TABLE"
            else "stored_text"
        )

        concepto = ConceptoOferta(
            oferta=documento.oferta,
            documento=documento,
            orden=order,
            titulo_original=title,
            descripcion_original=(
                description
            ),
            texto_normalizado=(
                _normalize_text(
                    title
                )
            ),
            cantidad=reviewed.get(
                "cantidad"
            ),
            unidad=(
                reviewed.get(
                    "unidad"
                )
                or ""
            ).strip()[:40],
            precio_unitario=(
                reviewed.get(
                    "precio_unitario"
                )
            ),
            importe=reviewed.get(
                "importe"
            ),
            alcance=scope,
            pagina=_positive_int(
                source.get(
                    "pagina"
                )
            ),
            linea_inicio=(
                _positive_int(
                    source.get(
                        "linea_inicio"
                    )
                )
            ),
            linea_fin=(
                _positive_int(
                    source.get(
                        "linea_fin"
                    )
                )
            ),
            evidencia=str(
                evidence
            ),
            origen=(
                ConceptoOferta
                .Origen
                .HUMANO
                if human_edited
                else
                ConceptoOferta
                .Origen
                .DETERMINISTA
            ),
            confianza_extraccion=(
                confidence
            ),
            raw_data={
                "v2c": {
                    "source_index": (
                        source_index
                    ),
                    "strategy": (
                        strategy
                    ),
                    "contexto": (
                        source.get(
                            "contexto"
                        )
                        or ""
                    ),
                    "evidence_source": (
                        evidence_source
                    ),
                    "human_confirmed": (
                        True
                    ),
                    "human_edited": (
                        human_edited
                    ),
                    "confirmed_by_user_id": (
                        getattr(
                            user,
                            "pk",
                            None,
                        )
                    ),
                    "source_document_sha256": (
                        documento.sha256
                    ),
                    "source": (
                        _json_safe(
                            source
                        )
                    ),
                }
            },
        )

        concepto.save()

        created.append(
            concepto
        )

    confirmed_reconciliation = (
        reconcile_concepts(
            [
                {
                    "alcance": concepto.alcance,
                    "importe": concepto.importe,
                }
                for concepto in created
            ],
            documento.oferta.base,
        )
    )

    datos = dict(
        documento.datos_extraidos
        or {}
    )

    datos[
        "conceptos_v2c"
    ] = {
        "confirmed": True,
        "count": len(created),
        "confirmed_by_user_id": (
            getattr(
                user,
                "pk",
                None,
            )
        ),
        "confirmed_at": (
            timezone.now()
            .isoformat()
        ),
        "source_reconciliation": (
            _json_safe(
                preview.get(
                    "reconciliacion"
                )
                or {}
            )
        ),
        "reconciliation": (
            _json_safe(
                confirmed_reconciliation
            )
        ),
    }

    documento.datos_extraidos = datos
    documento.estado_analisis = (
        "COMPLETADO"
    )
    documento.error_analisis = ""

    documento.save(
        update_fields=(
            "datos_extraidos",
            "estado_analisis",
            "error_analisis",
        )
    )

    return created


# COMPARATIVAS_V2C_EDIT_CONFIRMED_CONCEPTS_R1


class ConceptosConRelaciones(Exception):
    pass


def build_persisted_edit_initial(
    concepts,
):
    return [
        {
            "concept_id": item.pk,
            "titulo": (
                item.titulo_original
                or ""
            ),
            "descripcion": (
                item.descripcion_original
                or ""
            ),
            "cantidad": item.cantidad,
            "unidad": (
                item.unidad
                or ""
            ),
            "precio_unitario": (
                item.precio_unitario
            ),
            "importe": item.importe,
            "alcance": item.alcance,
        }
        for item in concepts
    ]


def _persisted_snapshot(
    concepto,
):
    return {
        "titulo": (
            concepto.titulo_original
            or ""
        ),
        "descripcion": (
            concepto.descripcion_original
            or ""
        ),
        "cantidad": concepto.cantidad,
        "unidad": (
            concepto.unidad
            or ""
        ),
        "precio_unitario": (
            concepto.precio_unitario
        ),
        "importe": concepto.importe,
        "alcance": concepto.alcance,
        "origen": concepto.origen,
        "confianza_extraccion": (
            concepto.confianza_extraccion
        ),
    }


def _reviewed_snapshot(
    reviewed,
):
    return {
        "titulo": (
            reviewed.get("titulo")
            or ""
        ).strip()[:500],
        "descripcion": (
            reviewed.get(
                "descripcion"
            )
            or ""
        ).strip(),
        "cantidad": reviewed.get(
            "cantidad"
        ),
        "unidad": (
            reviewed.get(
                "unidad"
            )
            or ""
        ).strip()[:40],
        "precio_unitario": (
            reviewed.get(
                "precio_unitario"
            )
        ),
        "importe": reviewed.get(
            "importe"
        ),
        "alcance": reviewed.get(
            "alcance"
        ),
    }


def _persisted_changed(
    before,
    after,
):
    keys = (
        "titulo",
        "descripcion",
        "cantidad",
        "unidad",
        "precio_unitario",
        "importe",
        "alcance",
    )

    return any(
        before.get(key)
        != after.get(key)
        for key in keys
    )


@transaction.atomic
def update_confirmed_concepts(
    *,
    documento_id,
    reviewed_rows,
    user,
):
    documento = (
        DocumentoComparativa.objects
        .select_for_update()
        .select_related(
            "oferta",
        )
        .get(
            pk=documento_id
        )
    )

    concepts = list(
        ConceptoOferta.objects
        .select_for_update()
        .filter(
            documento=documento
        )
        .order_by(
            "orden",
            "id",
        )
    )

    if not concepts:
        raise ValueError(
            "El documento no tiene "
            "conceptos confirmados."
        )

    if (
        ConceptoOferta.objects
        .filter(
            documento=documento,
            relaciones_comparacion__isnull=False,
        )
        .exists()
    ):
        raise ConceptosConRelaciones(
            "Existen relaciones de comparación "
            "sobre estos conceptos."
        )

    expected_ids = {
        item.pk
        for item in concepts
    }

    received_ids = []

    for row in reviewed_rows:
        try:
            concept_id = int(
                row["concept_id"]
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            raise ValueError(
                "Identificador de concepto "
                "no válido."
            )

        received_ids.append(
            concept_id
        )

    if (
        len(received_ids)
        != len(expected_ids)
        or len(
            set(received_ids)
        )
        != len(received_ids)
        or set(received_ids)
        != expected_ids
    ):
        raise ValueError(
            "El conjunto de conceptos "
            "ha cambiado o no es válido."
        )

    valid_scope = {
        choice[0]
        for choice
        in ConceptoOferta
        .Alcance
        .choices
    }

    by_id = {
        item.pk: item
        for item in concepts
    }

    changed = []

    now = timezone.now()

    for reviewed in reviewed_rows:
        concepto = by_id[
            int(
                reviewed[
                    "concept_id"
                ]
            )
        ]

        before = (
            _persisted_snapshot(
                concepto
            )
        )

        after = (
            _reviewed_snapshot(
                reviewed
            )
        )

        if (
            after["alcance"]
            not in valid_scope
        ):
            raise ValueError(
                "Alcance de concepto "
                "no válido."
            )

        if not after["titulo"]:
            raise ValueError(
                "El concepto debe tener "
                "un título."
            )

        if not _persisted_changed(
            before,
            after,
        ):
            continue

        raw = dict(
            concepto.raw_data
            or {}
        )

        v2c = dict(
            raw.get("v2c")
            or {}
        )

        history = list(
            v2c.get(
                "edit_history"
            )
            or []
        )

        history.append({
            "edited_at": (
                now.isoformat()
            ),
            "edited_by_user_id": (
                getattr(
                    user,
                    "pk",
                    None,
                )
            ),
            "before": (
                _json_safe(
                    before
                )
            ),
            "after": (
                _json_safe(
                    after
                )
            ),
        })

        v2c[
            "edit_history"
        ] = history

        v2c[
            "human_edited"
        ] = True

        v2c[
            "last_edited_at"
        ] = now.isoformat()

        v2c[
            "last_edited_by_user_id"
        ] = getattr(
            user,
            "pk",
            None,
        )

        raw["v2c"] = v2c

        concepto.titulo_original = (
            after["titulo"]
        )

        concepto.descripcion_original = (
            after["descripcion"]
        )

        concepto.texto_normalizado = (
            _normalize_text(
                after["titulo"]
            )
        )

        concepto.cantidad = (
            after["cantidad"]
        )

        concepto.unidad = (
            after["unidad"]
        )

        concepto.precio_unitario = (
            after[
                "precio_unitario"
            ]
        )

        concepto.importe = (
            after["importe"]
        )

        concepto.alcance = (
            after["alcance"]
        )

        concepto.origen = (
            ConceptoOferta
            .Origen
            .HUMANO
        )

        concepto.raw_data = raw

        # Evidencia, documento, página y líneas
        # NO se modifican.
        concepto.save()

        changed.append(
            concepto
        )

    reconciliation = (
        reconcile_concepts(
            [
                {
                    "alcance": item.alcance,
                    "importe": item.importe,
                }
                for item in (
                    ConceptoOferta.objects
                    .filter(
                        documento=documento
                    )
                    .order_by(
                        "orden",
                        "id",
                    )
                )
            ],
            documento.oferta.base,
        )
    )

    if changed:
        datos = dict(
            documento.datos_extraidos
            or {}
        )

        summary = dict(
            datos.get(
                "conceptos_v2c"
            )
            or {}
        )

        summary[
            "reconciliation"
        ] = _json_safe(
            reconciliation
        )

        summary[
            "last_edited_at"
        ] = now.isoformat()

        summary[
            "last_edited_by_user_id"
        ] = getattr(
            user,
            "pk",
            None,
        )

        summary[
            "last_edit_changed_count"
        ] = len(changed)

        summary[
            "edit_events"
        ] = int(
            summary.get(
                "edit_events"
            )
            or 0
        ) + 1

        datos[
            "conceptos_v2c"
        ] = summary

        documento.datos_extraidos = (
            datos
        )

        documento.save(
            update_fields=(
                "datos_extraidos",
            )
        )

    return {
        "changed": changed,
        "changed_count": len(
            changed
        ),
        "reconciliation": (
            reconciliation
        ),
    }
