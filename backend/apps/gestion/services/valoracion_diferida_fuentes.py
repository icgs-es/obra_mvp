"""
PORTAL INTASA
Fuente económica genérica para valoración diferida.

Responsabilidades:
- localizar el OCR almacenado de una factura;
- ejecutar el parser existente;
- normalizar su resultado;
- contrastar las líneas con la cabecera oficial;
- impedir uso automático de una fuente económica incoherente.

Este módulo NO escribe en base de datos.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


Q2 = Decimal("0.01")


def _dec(value, default=None):
    if value in (None, ""):
        return default

    try:
        return Decimal(
            str(value)
            .strip()
            .replace(" ", "")
            .replace(",", ".")
        )
    except (InvalidOperation, TypeError, ValueError):
        return default


def _money(value, default=None):
    d = _dec(value, default)

    if d is None:
        return None

    return d.quantize(
        Q2,
        rounding=ROUND_HALF_UP,
    )


def _parser_lines(parsed):
    if isinstance(parsed, dict):
        lines = parsed.get("lineas")

        if isinstance(lines, list):
            return lines

    if isinstance(parsed, list):
        return parsed

    return []


def _line_amount(item):
    if not isinstance(item, dict):
        return None

    for key in (
        "importe",
        "importe_linea",
        "importe_calculado",
    ):
        if key in item and item.get(key) not in (None, ""):
            return _money(item.get(key), None)

    return None


def sumar_base_lineas(lineas):
    total = Decimal("0.00")
    validas = 0

    for item in lineas or []:
        amount = _line_amount(item)

        if amount is None:
            continue

        total += amount
        validas += 1

    return (
        total.quantize(
            Q2,
            rounding=ROUND_HALF_UP,
        ),
        validas,
    )


def evaluar_fuente_economica(
    *,
    factura_base,
    parsed,
    tolerancia=Decimal("0.05"),
):
    """
    Evalúa únicamente coherencia económica.

    Estados:
    - CONFIABLE
    - INCOMPLETA
    - INCONSISTENTE
    - SIN_DATOS
    """

    base = _money(
        factura_base,
        None,
    )

    lineas = _parser_lines(parsed)

    base_lineas, lineas_con_importe = (
        sumar_base_lineas(lineas)
    )

    total_lineas = len(lineas)

    if not lineas:
        return {
            "estado": "SIN_DATOS",
            "auto_aplicar": False,
            "factura_base": base,
            "lineas_base": Decimal("0.00"),
            "lineas_total": 0,
            "lineas_con_importe": 0,
            "diferencia": (
                abs(base)
                if base is not None
                else None
            ),
            "razon": "PARSER_SIN_LINEAS",
        }

    if lineas_con_importe < total_lineas:
        return {
            "estado": "INCOMPLETA",
            "auto_aplicar": False,
            "factura_base": base,
            "lineas_base": base_lineas,
            "lineas_total": total_lineas,
            "lineas_con_importe": lineas_con_importe,
            "diferencia": (
                abs(base - base_lineas)
                if base is not None
                else None
            ),
            "razon": "LINEAS_SIN_IMPORTE_EXPLICITO",
        }

    if base is None:
        return {
            "estado": "INCOMPLETA",
            "auto_aplicar": False,
            "factura_base": None,
            "lineas_base": base_lineas,
            "lineas_total": total_lineas,
            "lineas_con_importe": lineas_con_importe,
            "diferencia": None,
            "razon": "CABECERA_SIN_BASE",
        }

    diferencia = abs(
        base - base_lineas
    ).quantize(
        Q2,
        rounding=ROUND_HALF_UP,
    )

    if diferencia <= tolerancia:
        return {
            "estado": "CONFIABLE",
            "auto_aplicar": True,
            "factura_base": base,
            "lineas_base": base_lineas,
            "lineas_total": total_lineas,
            "lineas_con_importe": lineas_con_importe,
            "diferencia": diferencia,
            "razon": "SUMA_LINEAS_CUADRA_CON_CABECERA",
        }

    return {
        "estado": "INCONSISTENTE",
        "auto_aplicar": False,
        "factura_base": base,
        "lineas_base": base_lineas,
        "lineas_total": total_lineas,
        "lineas_con_importe": lineas_con_importe,
        "diferencia": diferencia,
        "razon": "SUMA_LINEAS_NO_CUADRA_CON_CABECERA",
    }


def extraer_fuente_economica_factura(factura):
    """
    Lectura pura.

    Busca el último DocumentoCompraAdjunto de la factura
    que tenga texto OCR y ejecuta el parser ya registrado.
    """

    from django.apps import apps

    from apps.gestion.services.facturas_pdf import (
        extract_factura_lines_from_text,
    )

    DocumentoCompraAdjunto = apps.get_model(
        "gestion",
        "DocumentoCompraAdjunto",
    )

    adjunto = (
        DocumentoCompraAdjunto.objects
        .filter(
            factura=factura,
        )
        .exclude(
            ocr_texto="",
        )
        .order_by(
            "-creado_en",
            "-pk",
        )
        .first()
    )

    if not adjunto:
        return {
            "adjunto": None,
            "parsed": {
                "lineas": [],
            },
            "evaluacion": evaluar_fuente_economica(
                factura_base=getattr(
                    factura,
                    "importe_base_imponible",
                    None,
                ),
                parsed={
                    "lineas": [],
                },
            ),
        }

    text = adjunto.ocr_texto or ""

    parsed = extract_factura_lines_from_text(
        text
    )

    evaluacion = evaluar_fuente_economica(
        factura_base=getattr(
            factura,
            "importe_base_imponible",
            None,
        ),
        parsed=parsed,
    )

    return {
        "adjunto": adjunto,
        "parsed": parsed,
        "evaluacion": evaluacion,
    }
