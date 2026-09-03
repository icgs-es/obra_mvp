from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError


Q4 = Decimal("0.0001")
Q2 = Decimal("0.01")
CIEN = Decimal("100")


def decimal_seguro(value, default="0"):
    try:
        return Decimal(str(value if value not in (None, "") else default).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def calcular_linea_compra(
    *,
    cantidad,
    precio_unitario,
    descuento_porcentaje=0,
    descuento_adicional=0,
):
    cantidad = decimal_seguro(cantidad).quantize(Q4, rounding=ROUND_HALF_UP)
    precio = decimal_seguro(precio_unitario).quantize(Q4, rounding=ROUND_HALF_UP)
    porcentaje = decimal_seguro(descuento_porcentaje).quantize(Q2, rounding=ROUND_HALF_UP)
    adicional = decimal_seguro(descuento_adicional).quantize(Q2, rounding=ROUND_HALF_UP)

    if porcentaje < Decimal("0") or porcentaje > CIEN:
        raise ValidationError("El descuento debe estar comprendido entre 0 y 100 %.")

    if adicional < Decimal("0"):
        raise ValidationError("El descuento adicional no puede ser negativo.")

    bruto = (cantidad * precio).quantize(Q2, rounding=ROUND_HALF_UP)

    descuento_porcentaje_importe = (
        bruto * porcentaje / CIEN
    ).quantize(Q2, rounding=ROUND_HALF_UP)

    despues_porcentaje = (
        bruto - descuento_porcentaje_importe
    ).quantize(Q2, rounding=ROUND_HALF_UP)

    if bruto > 0 and adicional > despues_porcentaje:
        raise ValidationError(
            "El descuento adicional no puede superar la base restante de la línea."
        )

    base = (despues_porcentaje - adicional).quantize(
        Q2,
        rounding=ROUND_HALF_UP,
    )

    return {
        "cantidad": cantidad,
        "precio_unitario": precio,
        "descuento_porcentaje": porcentaje,
        "descuento_porcentaje_importe": descuento_porcentaje_importe,
        "descuento_adicional": adicional,
        "base_bruta": bruto,
        "base_despues_porcentaje": despues_porcentaje,
        "base_linea": base,
    }


def descuento_adicional_historico(linea):
    raw = linea.raw_data if isinstance(getattr(linea, "raw_data", None), dict) else {}

    if raw.get("descuento_semantica") == "PORCENTAJE_MAS_ADICIONAL_V1":
        return decimal_seguro(getattr(linea, "importe_descuento", 0)).quantize(Q2)

    porcentaje = decimal_seguro(getattr(linea, "descuento", 0))
    almacenado = decimal_seguro(getattr(linea, "importe_descuento", 0)).quantize(Q2)
    bruto = (
        decimal_seguro(getattr(linea, "cantidad", 0))
        * decimal_seguro(getattr(linea, "precio_unitario", 0))
    ).quantize(Q2, rounding=ROUND_HALF_UP)

    porcentaje_importe = (
        bruto * porcentaje / CIEN
    ).quantize(Q2, rounding=ROUND_HALF_UP)

    if porcentaje > 0 and (
        almacenado == Decimal("0.00")
        or abs(almacenado - porcentaje_importe) <= Decimal("0.02")
    ):
        return Decimal("0.00")

    return almacenado


def marcar_semantica_canonica(linea, resultado):
    raw = linea.raw_data if isinstance(getattr(linea, "raw_data", None), dict) else {}
    raw = dict(raw)

    raw["descuento_semantica"] = "PORCENTAJE_MAS_ADICIONAL_V1"
    raw["descuento_porcentaje"] = str(resultado["descuento_porcentaje"])
    raw["descuento_porcentaje_importe"] = str(
        resultado["descuento_porcentaje_importe"]
    )
    raw["importe_descuento_adicional"] = str(resultado["descuento_adicional"])
    raw["base_bruta"] = str(resultado["base_bruta"])
    raw["base_linea_canonica"] = str(resultado["base_linea"])

    linea.raw_data = raw
    return linea
