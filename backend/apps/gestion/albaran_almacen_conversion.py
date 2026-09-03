"""Conversión canónica de compra a unidad de almacén para albaranes.

Los datos introducidos en el navegador son sólo una previsualización. La
conversión que acaba en stock siempre se obtiene de la relación artículo-alias
autorizada y se calcula exclusivamente con ``Decimal``.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


Q4 = Decimal("0.0000")
Q2 = Decimal("0.01")
RECIPROCAL_TOLERANCE = Decimal("0.0001")
MONEY_TOLERANCE = Decimal("0.01")


class AlbaranAlmacenConversionError(ValueError):
    """Un dato de conversión no permite crear una entrada de almacén."""


def decimal_es(value, *, field_name):
    """Parse a decimal input without ever passing through ``float``."""
    try:
        text = str(value if value is not None else "").strip()
        text = (
            text.replace("€", "")
            .replace("EUR", "")
            .replace("\xa0", "")
            .replace(" ", "")
        )
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        else:
            text = text.replace(",", ".")
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise AlbaranAlmacenConversionError(
            f"{field_name} no es un decimal válido."
        ) from None


def q4(value):
    return Decimal(value).quantize(Q4, rounding=ROUND_HALF_UP)


def q2(value):
    return Decimal(value).quantize(Q2, rounding=ROUND_HALF_UP)


def normalizar_unidad(value):
    text = str(value or "").strip().upper()
    aliases = {
        "TONELADA": "TN",
        "TONELADAS": "TN",
        "TN": "TN",
        "CUBA": "CUBAS",
        "CUBAS": "CUBAS",
        "LITRO": "L",
        "LITROS": "L",
        "LTR": "L",
        "LTRS": "L",
        "LTS": "L",
    }
    return aliases.get(text, text)


@dataclass(frozen=True)
class ConversionAlmacen:
    cantidad_compra: Decimal
    unidad_compra: str
    precio_compra: Decimal
    importe_compra: Decimal
    cantidad_uso: Decimal
    unidad_uso: str
    precio_uso: Decimal
    importe_uso: Decimal
    factor_unidad_uso_por_compra: Decimal
    factor_compra_por_unidad_uso: Decimal
    alias_id: int | None


def conversion_compra_a_uso(
    *,
    cantidad_compra,
    unidad_compra,
    precio_compra,
    importe_compra,
    unidad_uso,
    alias=None,
    recurso_id=None,
):
    """Return an auditable canonical purchase-to-usage conversion.

    A configured alias must expose both reciprocal factors. Without configured
    factors only identical normalized units are accepted with factor one.
    """
    cantidad = q4(decimal_es(cantidad_compra, field_name="La cantidad de compra"))
    precio = q4(decimal_es(precio_compra, field_name="El precio de compra"))
    importe = q2(decimal_es(importe_compra, field_name="El importe de compra"))
    compra = normalizar_unidad(unidad_compra)
    uso = normalizar_unidad(unidad_uso)

    if cantidad <= 0:
        raise AlbaranAlmacenConversionError(
            "La cantidad de compra debe ser positiva."
        )
    if precio < 0:
        raise AlbaranAlmacenConversionError(
            "El precio de compra no puede ser negativo."
        )
    if not compra or not uso:
        raise AlbaranAlmacenConversionError(
            "Falta la unidad de compra o la unidad de almacén."
        )

    raw = getattr(alias, "raw_data", None) if alias is not None else None
    raw = raw if isinstance(raw, dict) else {}
    configured_resource_id = raw.get("recurso_catalogo_id")
    if (
        configured_resource_id not in (None, "")
        and recurso_id is not None
        and str(configured_resource_id) != str(recurso_id)
    ):
        raise AlbaranAlmacenConversionError(
            "La conversión configurada no corresponde al recurso de almacén."
        )

    factor_uso_raw = raw.get("factor_unidad_uso_por_compra")
    factor_compra_raw = raw.get("factor_compra_por_unidad_uso")
    if factor_uso_raw in (None, "") and factor_compra_raw in (None, ""):
        if compra != uso:
            raise AlbaranAlmacenConversionError(
                "No hay una conversión canónica válida entre la unidad de compra y la de almacén."
            )
        factor_uso = factor_compra = Decimal("1")
    elif factor_uso_raw in (None, "") or factor_compra_raw in (None, ""):
        raise AlbaranAlmacenConversionError(
            "La conversión configurada está incompleta."
        )
    else:
        factor_uso = decimal_es(
            factor_uso_raw,
            field_name="El factor de unidad de uso",
        )
        factor_compra = decimal_es(
            factor_compra_raw,
            field_name="El factor de unidad de compra",
        )
        if factor_uso <= 0 or factor_compra <= 0:
            raise AlbaranAlmacenConversionError(
                "Los factores de conversión deben ser positivos."
            )
        if abs((factor_uso * factor_compra) - Decimal("1")) > RECIPROCAL_TOLERANCE:
            raise AlbaranAlmacenConversionError(
                "Los factores de conversión configurados no son recíprocos."
            )

    if alias is not None:
        unidad_alias = normalizar_unidad(getattr(alias, "unidad_proveedor", ""))
        if unidad_alias and unidad_alias != compra:
            raise AlbaranAlmacenConversionError(
                "La unidad de compra no coincide con la configuración del proveedor."
            )

    cantidad_uso = q4(cantidad * factor_uso)
    precio_uso = q4(precio / factor_uso)
    importe_uso = q2(cantidad_uso * precio_uso)
    if abs(importe_uso - importe) > MONEY_TOLERANCE:
        raise AlbaranAlmacenConversionError(
            "La conversión no conserva el importe de la línea."
        )

    return ConversionAlmacen(
        cantidad_compra=cantidad,
        unidad_compra=compra,
        precio_compra=precio,
        importe_compra=importe,
        cantidad_uso=cantidad_uso,
        unidad_uso=uso,
        precio_uso=precio_uso,
        importe_uso=importe_uso,
        factor_unidad_uso_por_compra=factor_uso,
        factor_compra_por_unidad_uso=factor_compra,
        alias_id=getattr(alias, "pk", None),
    )
