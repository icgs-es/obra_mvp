"""
Preparación determinista para matching V2D.

No decide equivalencias entre proveedores.
No llama a IA.
No escribe en base de datos.

Solo condensa repeticiones estrictamente equivalentes
dentro de una misma oferta conservando todos los
ConceptoOferta originales.
"""

import hashlib
import re
import unicodedata

from decimal import Decimal


def _normalize_text(value):
    value = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )

    value = value.upper()

    value = re.sub(
        r"[^A-Z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def _normalize_unit(value):
    return _normalize_text(value)


def _decimal_key(value):
    if value is None:
        return ""

    return format(
        Decimal(value),
        "f",
    )


def _context_from_concept(concept):
    raw = (
        concept.raw_data
        if isinstance(
            concept.raw_data,
            dict,
        )
        else {}
    )

    v2c = (
        raw.get("v2c")
        if isinstance(
            raw.get("v2c"),
            dict,
        )
        else {}
    )

    return (
        v2c.get("contexto")
        or ""
    ).strip()


def _strict_signature(concept):
    return (
        concept.oferta_id,
        concept.alcance,
        _normalize_text(
            concept.titulo_original
        ),
        _normalize_unit(
            concept.unidad
        ),
        _decimal_key(
            concept.precio_unitario
        ),
    )


def _cluster_fingerprint(signature):
    raw = "|".join(
        str(item)
        for item in signature
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def _sum_if_complete(values):
    values = list(values)

    if not values:
        return None, False

    if any(
        value is None
        for value in values
    ):
        return None, False

    return (
        sum(
            (
                Decimal(value)
                for value in values
            ),
            Decimal("0"),
        ),
        True,
    )


def build_source_units(concepts):
    """
    Agrupa únicamente por firma estricta:

    - misma oferta;
    - mismo alcance;
    - mismo título normalizado;
    - misma unidad normalizada;
    - mismo precio unitario.

    El contexto se conserva como evidencia, pero no
    forma parte de la firma.
    """

    clusters = {}

    ordered = sorted(
        list(concepts),
        key=lambda item: (
            item.oferta_id,
            item.orden,
            item.pk,
        ),
    )

    for concept in ordered:
        signature = (
            _strict_signature(
                concept
            )
        )

        cluster = clusters.get(
            signature
        )

        if cluster is None:
            supplier = (
                concept
                .oferta
                .ofertante
            )

            cluster = {
                "fingerprint": (
                    _cluster_fingerprint(
                        signature
                    )
                ),
                "oferta_id": (
                    concept.oferta_id
                ),
                "ofertante_id": (
                    supplier.pk
                ),
                "ofertante_nombre": (
                    supplier.nombre
                ),
                "alcance": (
                    concept.alcance
                ),
                "titulo": (
                    concept.titulo_original
                    or ""
                ),
                "titulo_normalizado": (
                    signature[2]
                ),
                "unidad": (
                    concept.unidad
                    or ""
                ),
                "unidad_normalizada": (
                    signature[3]
                ),
                "precio_unitario": (
                    concept.precio_unitario
                ),
                "member_ids": [],
                "member_orders": [],
                "contexts": [],
                "pages": [],
                "_quantities": [],
                "_amounts": [],
            }

            clusters[
                signature
            ] = cluster

        cluster[
            "member_ids"
        ].append(
            concept.pk
        )

        cluster[
            "member_orders"
        ].append(
            concept.orden
        )

        context = (
            _context_from_concept(
                concept
            )
        )

        if (
            context
            and context
            not in cluster["contexts"]
        ):
            cluster[
                "contexts"
            ].append(
                context
            )

        if (
            concept.pagina is not None
            and concept.pagina
            not in cluster["pages"]
        ):
            cluster[
                "pages"
            ].append(
                concept.pagina
            )

        cluster[
            "_quantities"
        ].append(
            concept.cantidad
        )

        cluster[
            "_amounts"
        ].append(
            concept.importe
        )

    units = []

    for cluster in clusters.values():
        (
            quantity_sum,
            quantity_complete,
        ) = _sum_if_complete(
            cluster.pop(
                "_quantities"
            )
        )

        (
            amount_sum,
            amount_complete,
        ) = _sum_if_complete(
            cluster.pop(
                "_amounts"
            )
        )

        cluster[
            "source_count"
        ] = len(
            cluster[
                "member_ids"
            ]
        )

        cluster[
            "aggregation"
        ] = (
            "EXACT_AGGREGATE"
            if cluster["source_count"] > 1
            else "SINGLE"
        )

        cluster[
            "cantidad_total"
        ] = quantity_sum

        cluster[
            "cantidad_completa"
        ] = quantity_complete

        cluster[
            "importe_total"
        ] = amount_sum

        cluster[
            "importe_completo"
        ] = amount_complete

        units.append(cluster)

    units.sort(
        key=lambda item: (
            item["oferta_id"],
            min(
                item[
                    "member_orders"
                ]
            ),
            min(
                item[
                    "member_ids"
                ]
            ),
        )
    )

    return units


def _json_decimal(value):
    if value is None:
        return None

    return format(
        Decimal(value),
        "f",
    )


def serialize_source_units(units):
    result = []

    for unit in units:
        result.append({
            "fingerprint": (
                unit["fingerprint"]
            ),
            "oferta_id": (
                unit["oferta_id"]
            ),
            "ofertante_id": (
                unit["ofertante_id"]
            ),
            "ofertante_nombre": (
                unit[
                    "ofertante_nombre"
                ]
            ),
            "alcance": (
                unit["alcance"]
            ),
            "titulo": (
                unit["titulo"]
            ),
            "titulo_normalizado": (
                unit[
                    "titulo_normalizado"
                ]
            ),
            "unidad": (
                unit["unidad"]
            ),
            "precio_unitario": (
                _json_decimal(
                    unit[
                        "precio_unitario"
                    ]
                )
            ),
            "member_ids": list(
                unit["member_ids"]
            ),
            "contexts": list(
                unit["contexts"]
            ),
            "pages": list(
                unit["pages"]
            ),
            "source_count": (
                unit["source_count"]
            ),
            "aggregation": (
                unit["aggregation"]
            ),
            "cantidad_total": (
                _json_decimal(
                    unit[
                        "cantidad_total"
                    ]
                )
            ),
            "cantidad_completa": (
                unit[
                    "cantidad_completa"
                ]
            ),
            "importe_total": (
                _json_decimal(
                    unit[
                        "importe_total"
                    ]
                )
            ),
            "importe_completo": (
                unit[
                    "importe_completo"
                ]
            ),
        })

    return result


def summarize_source_units(units):
    by_supplier = {}

    for unit in units:
        key = unit[
            "ofertante_id"
        ]

        summary = by_supplier.setdefault(
            key,
            {
                "ofertante_id": key,
                "ofertante_nombre": (
                    unit[
                        "ofertante_nombre"
                    ]
                ),
                "units": 0,
                "source_concepts": 0,
                "aggregated_units": 0,
            },
        )

        summary["units"] += 1

        summary[
            "source_concepts"
        ] += unit[
            "source_count"
        ]

        if unit[
            "source_count"
        ] > 1:
            summary[
                "aggregated_units"
            ] += 1

    return sorted(
        by_supplier.values(),
        key=lambda item: (
            item["ofertante_id"]
        ),
    )
