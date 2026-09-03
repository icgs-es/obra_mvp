"""
Comparativa ejecutiva IA.

Una comparativa ya normalizada se entrega a INTASA IA
para obtener un informe ejecutivo breve.

Este módulo:
- usa siempre la última versión de cada ofertante;
- no adjudica;
- no crea grupos ni relaciones;
- no modifica datos de negocio;
- no conoce OpenAI directamente.
"""

from collections import defaultdict

from .matching_prepare import (
    build_source_units,
    serialize_source_units,
)
from .models import (
    ConceptoOferta,
    Oferta,
)


EXECUTIVE_SCHEMA_NAME = (
    "comparativas_executive_v1"
)

EXECUTIVE_SCHEMA_VERSION = "v1"

COMPARABILIDAD = (
    "ALTA",
    "MEDIA",
    "BAJA",
    "NO_DETERMINABLE",
)


class ExecutiveIAError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = str(code)


def _decimal_text(value):
    if value is None:
        return None

    return str(value)


def _date_text(value):
    if value is None:
        return None

    return value.isoformat()


def _compact_source_unit(unit):
    contexts = [
        str(value)
        for value in (
            unit.get("contexts")
            or []
        )
        if str(value).strip()
    ]

    return {
        "alcance": str(
            unit.get(
                "alcance",
                "",
            )
        ),
        "concepto": str(
            unit.get(
                "titulo",
                "",
            )
        ),
        "cantidad": (
            unit.get(
                "cantidad_total"
            )
        ),
        "unidad": str(
            unit.get(
                "unidad",
                "",
            )
        ),
        "precio_unitario": (
            unit.get(
                "precio_unitario"
            )
        ),
        "importe": (
            unit.get(
                "importe_total"
            )
        ),
        "repeticiones": int(
            unit.get(
                "source_count",
                1,
            )
        ),
        "contexto": (
            " | ".join(
                contexts
            )[:300]
        ),
    }


def _validate_offer_ids(
    offer_ids,
):
    if not isinstance(
        offer_ids,
        list,
    ):
        raise ExecutiveIAError(
            "offer_ids_invalid"
        )

    normalized = []

    for value in offer_ids:
        try:
            value = int(value)
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ExecutiveIAError(
                "offer_id_invalid"
            ) from exc

        if value <= 0:
            raise ExecutiveIAError(
                "offer_id_invalid"
            )

        normalized.append(value)

    if len(normalized) < 2:
        raise ExecutiveIAError(
            "minimum_two_offers_required"
        )

    if len(set(normalized)) != len(
        normalized
    ):
        raise ExecutiveIAError(
            "offer_ids_duplicate"
        )

    return normalized


def build_executive_schema(
    offer_ids,
):
    offer_ids = _validate_offer_ids(
        offer_ids
    )

    return {
        "type": "object",
        "properties": {
            "version": {
                "type": "string",
                "enum": [
                    EXECUTIVE_SCHEMA_VERSION
                ],
            },
            "resumen": {
                "type": "string",
                "minLength": 1,
                "maxLength": 300,
            },
            "por_oferta": {
                "type": "array",
                "minItems": len(
                    offer_ids
                ),
                "maxItems": len(
                    offer_ids
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "oferta_id": {
                            "type": "integer",
                            "enum": (
                                offer_ids
                            ),
                        },
                        "comparabilidad": {
                            "type": "string",
                            "enum": list(
                                COMPARABILIDAD
                            ),
                        },
                        "comentario": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 180,
                        },
                    },
                    "required": [
                        "oferta_id",
                        "comparabilidad",
                        "comentario",
                    ],
                    "additionalProperties": (
                        False
                    ),
                },
            },
            "diferencias_clave": {
                "type": "array",
                "minItems": 1,
                "maxItems": 2,
                "items": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 180,
                },
            },
            "riesgos_y_aclaraciones": {
                "type": "array",
                "maxItems": 2,
                "items": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 180,
                },
            },
            "opcion_orientativa_oferta_id": {
                "type": "integer",
                "enum": (
                    [0]
                    + offer_ids
                ),
            },
            "recomendacion": {
                "type": "string",
                "minLength": 1,
                "maxLength": 280,
            },
        },
        "required": [
            "version",
            "resumen",
            "por_oferta",
            "diferencias_clave",
            "riesgos_y_aclaraciones",
            "opcion_orientativa_oferta_id",
            "recomendacion",
        ],
        "additionalProperties": False,
    }


def build_executive_instructions():
    return """
Actúa como analista técnico de compras y contratación.

Recibirás varias ofertas de un mismo expediente con
importes y conceptos previamente normalizados.

Produce una comparativa ejecutiva MUY BREVE, clara,
exacta y útil para Gerencia.

REGLAS OBLIGATORIAS:

1. Usa exclusivamente los datos recibidos. No inventes.

2. impuestos = null significa NO INFORMADO.
   Nunca supongas que el impuesto está incluido.

3. COMPARABILIDAD significa equivalencia real de alcance,
   cantidades, tipología, unidades y prestaciones respecto
   al expediente. NO significa que el presupuesto esté
   mejor redactado o sea más detallado.

4. Clasifica la comparabilidad con este criterio:
   ALTA = el alcance documentado es materialmente equivalente
   al expediente; solo quedan aclaraciones menores que no
   impiden comparar directamente la base económica.
   MEDIA = existe una base razonable de comparación, pero hay
   uno o más aspectos relevantes de alcance que deben
   confirmarse antes de una comparación económica directa.
   BAJA = existen diferencias materiales conocidas de alcance,
   cantidades, tipología, unidades o prestaciones.
   NO_DETERMINABLE = la documentación disponible no permite
   decidir con suficiente fundamento si el alcance es
   equivalente.

   Un presupuesto muy detallado puede ser MEDIA, BAJA o
   NO_DETERMINABLE. El mayor detalle documental nunca
   convierte por sí mismo una oferta en ALTA.

5. Una oferta más barata tampoco es automáticamente mejor
   si contiene menos alcance.

6. Considera expresamente conceptos INCLUIDOS y EXCLUIDOS.

7. Diferencias en número de viviendas, baños, cocinas,
   cantidades, suministros, montaje, contadores, sanitarios,
   grifería, albañilería o permisos son diferencias
   materiales cuando afecten a la comparación.

8. NO eliges proveedor. Devuelve siempre
   opcion_orientativa_oferta_id = 0. La aplicación aplicará
   después una regla local y determinista de gobierno.

9. Tu responsabilidad es clasificar correctamente la
   comparabilidad y explicar las diferencias de alcance.
   La opción final nunca depende del mayor detalle documental,
   de que un documento sea más largo o esté mejor redactado.

10. No adjudicas, no autorizas compras ni tomas decisiones.

11. Nunca escribas "oferta 1", "oferta 2", "oferta 3",
    etc. Utiliza siempre el nombre del proveedor.

12. Escribe frases cortas y COMPLETAS. Nunca cortes una
    palabra ni dejes una frase sin terminar. Si una idea
    resulta demasiado larga, resúmela antes de alcanzar
    el límite del campo.

13. Evita repetir la misma observación en varios apartados.

14. Limita diferencias_clave a las 2 diferencias más
    importantes y riesgos_y_aclaraciones a los 2 puntos
    realmente decisivos.

15. La recomendación final debe ser breve y decir qué debe
    comprobarse antes de contratar.

El informe debe poder leerse en menos de un minuto y caber
cómodamente en una página A4.
""".strip()


def prepare_executive_data(
    comparativa,
):
    offers_qs = (
        Oferta.objects
        .filter(
            ofertante__comparativa=(
                comparativa
            )
        )
        .select_related(
            "ofertante"
        )
        .order_by(
            "ofertante_id",
            "-version",
            "-id",
        )
    )

    latest_offers = []
    seen_bidders = set()

    for offer in offers_qs:
        if (
            offer.ofertante_id
            in seen_bidders
        ):
            continue

        seen_bidders.add(
            offer.ofertante_id
        )

        latest_offers.append(
            offer
        )

    latest_offers.sort(
        key=lambda value: (
            value.ofertante.nombre.lower(),
            value.id,
        )
    )

    offer_ids = [
        offer.id
        for offer in latest_offers
    ]

    concepts = []

    if offer_ids:
        concepts = list(
            ConceptoOferta.objects
            .filter(
                oferta_id__in=offer_ids
            )
            .select_related(
                "oferta",
                "oferta__ofertante",
            )
            .order_by(
                "oferta_id",
                "orden",
                "id",
            )
        )

    source_units = []

    if concepts:
        source_units = (
            serialize_source_units(
                build_source_units(
                    concepts
                )
            )
        )

    units_by_offer = defaultdict(
        list
    )

    for unit in source_units:
        units_by_offer[
            int(
                unit["oferta_id"]
            )
        ].append(
            _compact_source_unit(
                unit
            )
        )

    rows = []
    payload_offers = []

    for offer in latest_offers:
        rows.append({
            "oferta_id": offer.id,
            "nombre": (
                offer.ofertante.nombre
            ),
            "version": offer.version,
            "fecha_documento": (
                offer.fecha_documento
            ),
            "referencia": (
                offer.referencia
            ),
            "moneda": (
                offer.moneda
            ),
            "base": offer.base,
            "impuestos": (
                offer.impuestos
            ),
            "total": offer.total,
            "partidas": len(
                units_by_offer[
                    offer.id
                ]
            ),
        })

        payload_offers.append({
            "oferta_id": offer.id,
            "proveedor": (
                offer.ofertante.nombre
            ),
            "version": (
                offer.version
            ),
            "fecha": _date_text(
                offer.fecha_documento
            ),
            "referencia": str(
                offer.referencia
                or ""
            ),
            "moneda": str(
                offer.moneda
                or ""
            ),
            "base": _decimal_text(
                offer.base
            ),
            "impuestos": (
                _decimal_text(
                    offer.impuestos
                )
            ),
            "total": _decimal_text(
                offer.total
            ),
            "observaciones": str(
                offer.observaciones
                or ""
            )[:1000],
            "partidas": (
                units_by_offer[
                    offer.id
                ]
            ),
        })

    can_generate = (
        len(latest_offers) >= 2
        and bool(source_units)
    )

    blocking_reason = ""

    if len(latest_offers) < 2:
        blocking_reason = (
            "Se necesitan al menos "
            "dos ofertas."
        )

    elif not source_units:
        blocking_reason = (
            "No hay conceptos confirmados "
            "para analizar."
        )

    payload = {
        "expediente": {
            "titulo": str(
                comparativa.titulo
                or ""
            ),
            "categoria": str(
                comparativa.categoria
                or ""
            ),
            "alcance": str(
                comparativa.descripcion
                or ""
            ),
            "referencia": {
                "tipo": str(
                    comparativa.referencia_tipo
                    or ""
                ),
                "codigo": str(
                    comparativa.referencia_codigo
                    or ""
                ),
                "nombre": str(
                    comparativa.referencia_nombre
                    or ""
                ),
            },
        },
        "ofertas": payload_offers,
    }

    return {
        "rows": rows,
        "offer_ids": offer_ids,
        "source_units_count": len(
            source_units
        ),
        "concepts_count": len(
            concepts
        ),
        "can_generate": (
            can_generate
        ),
        "blocking_reason": (
            blocking_reason
        ),
        "payload": payload,
    }


def validate_executive_report(
    report,
    *,
    offer_ids,
):
    offer_ids = _validate_offer_ids(
        offer_ids
    )

    if not isinstance(
        report,
        dict,
    ):
        raise ExecutiveIAError(
            "report_invalid"
        )

    if (
        report.get("version")
        != EXECUTIVE_SCHEMA_VERSION
    ):
        raise ExecutiveIAError(
            "report_version_invalid"
        )

    per_offer = report.get(
        "por_oferta"
    )

    if not isinstance(
        per_offer,
        list,
    ):
        raise ExecutiveIAError(
            "report_offers_invalid"
        )

    returned_ids = []

    for item in per_offer:
        if not isinstance(
            item,
            dict,
        ):
            raise ExecutiveIAError(
                "report_offer_invalid"
            )

        try:
            offer_id = int(
                item.get(
                    "oferta_id"
                )
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise ExecutiveIAError(
                "report_offer_id_invalid"
            ) from exc

        returned_ids.append(
            offer_id
        )

        if (
            item.get(
                "comparabilidad"
            )
            not in COMPARABILIDAD
        ):
            raise ExecutiveIAError(
                "report_comparability_invalid"
            )

    if len(
        set(returned_ids)
    ) != len(returned_ids):
        raise ExecutiveIAError(
            "report_offer_duplicate"
        )

    if set(
        returned_ids
    ) != set(
        offer_ids
    ):
        raise ExecutiveIAError(
            "report_offer_coverage_invalid"
        )

    option_id = report.get(
        "opcion_orientativa_oferta_id"
    )

    try:
        option_id = int(
            option_id
        )
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ExecutiveIAError(
            "report_option_invalid"
        ) from exc

    if (
        option_id != 0
        and option_id
        not in offer_ids
    ):
        raise ExecutiveIAError(
            "report_option_unknown"
        )

    return report


def _complete_fragment(
    value,
    *,
    limit,
):
    text = " ".join(
        str(value or "").split()
    ).strip()

    if not text:
        return ""

    if text.endswith(
        (
            ".",
            "!",
            "?",
        )
    ):
        return text

    if len(text) < max(
        1,
        int(limit) - 3,
    ):
        return (
            text.rstrip(" ,;:")
            + "."
        )

    minimum = max(
        10,
        len(text) // 4,
    )

    positions = [
        text.rfind("."),
        text.rfind("!"),
        text.rfind("?"),
        text.rfind(";"),
    ]

    position = max(
        positions
    )

    if position >= minimum:
        result = text[
            :position + 1
        ].strip()

        if result.endswith(";"):
            result = (
                result[:-1]
                .rstrip()
                + "."
            )

        return result

    comma = text.rfind(",")

    if comma >= minimum:
        return (
            text[:comma]
            .rstrip(" ,;:")
            + "."
        )

    words = text.split()

    if len(words) > 12:
        return (
            " ".join(
                words[:12]
            )
            .rstrip(" ,;:")
            + "."
        )

    return (
        text.rstrip(" ,;:")
        + "."
    )


def _sanitize_executive_texts(
    report,
):
    sanitized = dict(
        report
    )

    sanitized["resumen"] = (
        _complete_fragment(
            sanitized.get(
                "resumen"
            ),
            limit=300,
        )
    )

    per_offer = []

    for item in (
        sanitized.get(
            "por_oferta"
        )
        or []
    ):
        clean_item = dict(
            item
        )

        clean_item["comentario"] = (
            _complete_fragment(
                clean_item.get(
                    "comentario"
                ),
                limit=180,
            )
        )

        per_offer.append(
            clean_item
        )

    sanitized[
        "por_oferta"
    ] = per_offer

    sanitized[
        "diferencias_clave"
    ] = [
        _complete_fragment(
            item,
            limit=180,
        )
        for item in (
            sanitized.get(
                "diferencias_clave"
            )
            or []
        )
    ]

    sanitized[
        "riesgos_y_aclaraciones"
    ] = [
        _complete_fragment(
            item,
            limit=180,
        )
        for item in (
            sanitized.get(
                "riesgos_y_aclaraciones"
            )
            or []
        )
    ]

    return sanitized


def _format_report_money(
    value,
    currency,
):
    if value is None:
        return "—"

    try:
        text = f"{value:,.2f}"
    except (
        TypeError,
        ValueError,
    ):
        return str(value)

    text = (
        text
        .replace(",", "__THOUSAND__")
        .replace(".", ",")
        .replace(
            "__THOUSAND__",
            ".",
        )
    )

    currency = str(
        currency or ""
    ).strip().upper()

    if currency == "EUR":
        suffix = " €"
    elif currency:
        suffix = (
            " "
            + currency
        )
    else:
        suffix = ""

    return text + suffix


def govern_executive_report(
    *,
    prepared,
    report,
):
    """
    Gobierno ejecutivo V1.6.

    La IA clasifica comparabilidad.
    Python determina la opción orientativa.

    ALTA:
        elegible para opción provisional.

    MEDIA:
        alternativa que requiere aclaración.
        Nunca bloquea una ALTA.

    BAJA / NO_DETERMINABLE:
        fuera de selección económica directa.

    Entre las ALTA se elige la menor base,
    siempre dentro de una moneda homogénea.
    """
    if not isinstance(
        prepared,
        dict,
    ):
        raise ExecutiveIAError(
            "prepared_invalid"
        )

    if not isinstance(
        report,
        dict,
    ):
        raise ExecutiveIAError(
            "report_invalid"
        )

    rows = (
        prepared.get("rows")
        or []
    )

    if not rows:
        return report

    governed = (
        _sanitize_executive_texts(
            report
        )
    )

    ia_by_id = {}

    for item in (
        governed.get(
            "por_oferta"
        )
        or []
    ):
        try:
            offer_id = int(
                item.get(
                    "oferta_id"
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        ia_by_id[
            offer_id
        ] = item

    high = []
    medium = []

    for row in rows:
        try:
            offer_id = int(
                row.get(
                    "oferta_id"
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        ia = ia_by_id.get(
            offer_id
        )

        if not ia:
            continue

        comparability = (
            ia.get(
                "comparabilidad"
            )
        )

        if comparability not in (
            "ALTA",
            "MEDIA",
        ):
            continue

        base = row.get(
            "base"
        )

        if (
            base is None
            or base <= 0
        ):
            continue

        candidate = {
            "oferta_id": offer_id,
            "nombre": str(
                row.get(
                    "nombre"
                )
                or ""
            ),
            "base": base,
            "moneda": str(
                row.get(
                    "moneda"
                )
                or ""
            ).strip().upper(),
            "impuestos": (
                row.get(
                    "impuestos"
                )
            ),
            "comparabilidad": (
                comparability
            ),
        }

        if comparability == "ALTA":
            high.append(
                candidate
            )
        else:
            medium.append(
                candidate
            )

    option_id = 0
    option_name = ""

    # No se comparan económicamente ALTA de monedas
    # diferentes.
    high_currencies = {
        item["moneda"]
        for item in high
        if item["moneda"]
    }

    homogeneous_high = (
        bool(high)
        and len(high_currencies) == 1
        and all(
            item["moneda"]
            in high_currencies
            for item in high
        )
    )

    if homogeneous_high:
        high.sort(
            key=lambda item: (
                item["base"],
                item["oferta_id"],
            )
        )

        selected = high[0]

        option_id = (
            selected[
                "oferta_id"
            ]
        )

        option_name = (
            selected[
                "nombre"
            ]
        )

        currency = (
            selected[
                "moneda"
            ]
        )

        parts = [
            (
                f"{option_name} queda como opción "
                "orientativa provisional, con una base de "
                f"{_format_report_money(selected['base'], currency)}, "
                "al ser la oferta de menor base entre las "
                "clasificadas con comparabilidad alta."
            )
        ]

        # Segunda ALTA comparable.
        if len(high) >= 2:
            second = high[1]

            if (
                second["moneda"]
                == currency
            ):
                delta = (
                    second["base"]
                    - selected["base"]
                )

                parts.append(
                    (
                        f"{second['nombre']} es la siguiente "
                        "oferta comparable, con una base de "
                        f"{_format_report_money(second['base'], currency)} "
                        f"({_format_report_money(delta, currency)} más)."
                    )
                )

        # MEDIA más barata que la opción ALTA.
        cheaper_medium = [
            item
            for item in medium
            if (
                item["moneda"]
                == currency
                and item["base"]
                < selected["base"]
            )
        ]

        if cheaper_medium:
            cheaper_medium.sort(
                key=lambda item: (
                    item["base"],
                    item[
                        "oferta_id"
                    ],
                )
            )

            alternative = (
                cheaper_medium[0]
            )

            saving = (
                selected["base"]
                - alternative["base"]
            )

            parts.append(
                (
                    f"{alternative['nombre']} presenta una "
                    "base inferior en "
                    f"{_format_report_money(saving, currency)}, "
                    "pero su comparabilidad es media; conviene "
                    "aclarar y homogeneizar su alcance antes "
                    "de descartarla o contratar."
                )
            )

        if (
            selected[
                "impuestos"
            ]
            is None
        ):
            parts.append(
                (
                    f"Antes de contratar con {option_name}, "
                    "confirmar además los impuestos, que "
                    "actualmente no están informados."
                )
            )

        governed[
            "recomendacion"
        ] = " ".join(parts)

    else:
        governed[
            "recomendacion"
        ] = (
            "Sin opción orientativa provisional. No existe "
            "ninguna oferta con comparabilidad alta y base "
            "económica directamente comparable en una moneda "
            "homogénea. Conviene aclarar o reofertar los "
            "alcances pendientes antes de decidir."
        )

    governed[
        "opcion_orientativa_oferta_id"
    ] = option_id

    return governed


def request_executive_report(
    *,
    prepared,
    user,
    team=None,
    requester=None,
):
    if not isinstance(
        prepared,
        dict,
    ):
        raise ExecutiveIAError(
            "prepared_invalid"
        )

    if not prepared.get(
        "can_generate"
    ):
        raise ExecutiveIAError(
            "comparison_not_ready"
        )

    offer_ids = (
        prepared.get(
            "offer_ids"
        )
        or []
    )

    schema = build_executive_schema(
        offer_ids
    )

    if requester is None:
        from intasa_ia.services import (
            solicitar_json_estructurado,
        )

        requester = (
            solicitar_json_estructurado
        )

    result = requester(
        instructions=(
            build_executive_instructions()
        ),
        payload=(
            prepared["payload"]
        ),
        schema_name=(
            EXECUTIVE_SCHEMA_NAME
        ),
        schema=schema,
        user=user,
        team=team,
        metadata={
            "consumer": "comparativas",
            "operation": (
                "executive_comparison_v1"
            ),
            "offer_count": len(
                offer_ids
            ),
            "source_units": (
                prepared[
                    "source_units_count"
                ]
            ),
        },
        max_output_tokens=2000,
        timeout_seconds=90,
    )

    if not isinstance(
        result,
        dict,
    ):
        raise ExecutiveIAError(
            "structured_result_invalid"
        )

    report = result.get(
        "datos"
    )

    validate_executive_report(
        report,
        offer_ids=offer_ids,
    )

    result["datos"] = (
        govern_executive_report(
            prepared=prepared,
            report=report,
        )
    )

    return result
