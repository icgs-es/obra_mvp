"""Reglas canónicas de retención para facturas de proveedor.

La retención nunca modifica la base ni el IVA: solamente reduce el importe
pendiente de pago.  Este módulo se usa desde formularios, OCR y recálculos.
"""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def decimal(value, default=ZERO):
    """Convierte importes españoles o técnicos a Decimal sin redondear."""
    if value is None or value == "":
        return default
    raw = str(value).strip().replace("€", "").replace("EUR", "")
    raw = raw.replace(" ", "").replace("\xa0", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return default


def money(value):
    return decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def calcular(base, iva, porcentaje=ZERO):
    """Devuelve retención, bruto y neto con el redondeo contable único."""
    base = money(base)
    iva = money(iva)
    porcentaje = decimal(porcentaje)
    if porcentaje < ZERO:
        raise ValueError("El porcentaje de retención no puede ser negativo.")
    retencion = (base * porcentaje / Decimal("100")).quantize(
        CENT, rounding=ROUND_HALF_UP
    )
    bruto = (base + iva).quantize(CENT, rounding=ROUND_HALF_UP)
    return {
        "base": base,
        "iva": iva,
        "porcentaje": porcentaje.quantize(CENT, rounding=ROUND_HALF_UP),
        "retencion": retencion,
        "total_bruto": bruto,
        "importe_a_pagar": (bruto - retencion).quantize(CENT, rounding=ROUND_HALF_UP),
    }


def aplicar_a_factura(factura):
    """Sin guardar, sincroniza los campos persistidos de una factura."""
    result = calcular(
        factura.importe_base_imponible,
        factura.importe_iva,
        getattr(factura, "retencion_porcentaje", ZERO),
    )
    factura.retencion_porcentaje = result["porcentaje"]
    factura.retencion = result["retencion"]
    factura.tiene_retencion = result["retencion"] != ZERO
    factura.importe_factura = result["importe_a_pagar"]
    return result


_PCT_PATTERNS = (
    re.compile(r"(?i)(?P<pct>\d{1,2}(?:[,.]\d{1,2})?)\s*%\s*(?:de\s+)?retenci[oó]n"),
    re.compile(r"(?i)retenci[oó]n\s*(?:del?|:)?\s*(?P<pct>\d{1,2}(?:[,.]\d{1,2})?)\s*%"),
)
_AMOUNT_PATTERN = re.compile(
    r"(?i)retenci[oó]n(?:\s*\([^)]*\))?\s*[:\-]?\s*"
    r"(?P<amount>-?\d{1,3}(?:[.]\d{3})*(?:,\d{2})|-?\d+(?:[.,]\d{2}))"
)


def detectar_en_texto(texto):
    """Extrae porcentaje e importe explícitos, sin conocer ningún proveedor."""
    text = str(texto or "")
    porcentaje = None
    for pattern in _PCT_PATTERNS:
        match = pattern.search(text)
        if match:
            porcentaje = decimal(match.group("pct"), None)
            break
    amount_match = _AMOUNT_PATTERN.search(text)
    importe = decimal(amount_match.group("amount"), None) if amount_match else None
    return {"porcentaje": porcentaje, "importe": importe}


def aplicar_ocr(payload, proveedor=None):
    """Añade la retención OCR al payload y prioriza siempre el documento.

    Si el PDF no habla de retención se propone, sin confirmar automáticamente,
    la configuración habitual del proveedor.  Nunca se usa esa configuración
    para sobrescribir un valor detectado.
    """
    payload = payload if isinstance(payload, dict) else {}
    text = "\n".join(str(payload.get(key) or "") for key in ("text", "raw_extract"))
    found = detectar_en_texto(text)
    base = payload.get("base_imponible") or payload.get("importe_base_imponible") or payload.get("base")
    iva = payload.get("iva") or payload.get("importe_iva") or ZERO
    proposed = bool(getattr(proveedor, "aplica_retencion_habitual", False))
    habitual = getattr(proveedor, "retencion_habitual_porcentaje", ZERO) if proveedor else ZERO
    source = "OCR" if found["porcentaje"] is not None or found["importe"] is not None else ""
    porcentaje = found["porcentaje"]
    warning = ""
    if porcentaje is None and source == "" and proposed:
        porcentaje = decimal(habitual)
        source = "HABITUAL_PROPUESTA"
    if porcentaje is not None and base not in (None, ""):
        totals = calcular(base, iva, porcentaje)
        payload["retencion_porcentaje"] = str(totals["porcentaje"])
        payload["retencion"] = str(totals["retencion"])
        payload["importe_retencion"] = str(totals["retencion"])
        payload["total_bruto"] = str(totals["total_bruto"])
        payload["importe_factura"] = str(totals["importe_a_pagar"])
        payload["total"] = str(totals["importe_a_pagar"])
        if source == "OCR" and proposed and decimal(habitual) != totals["porcentaje"]:
            warning = (
                "El PDF indica una retención distinta de la habitual del proveedor; "
                "se ha priorizado el PDF."
            )
    elif found["importe"] is not None:
        # Se conserva como detección, pero no se inventa un porcentaje sin base.
        payload["retencion"] = str(money(found["importe"]))
        payload["importe_retencion"] = str(money(found["importe"]))
    payload["retencion_fuente"] = source
    if warning:
        payload["retencion_aviso"] = warning
    return payload
