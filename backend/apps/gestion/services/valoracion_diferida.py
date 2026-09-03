"""
PORTAL INTASA
Motor genérico de valoración diferida albarán -> factura.

Principios:
- Albarán = evidencia logística.
- Factura = evidencia económica.
- Matching y propuesta son read-only.
- No crear artículos/alias desde este módulo.
- Cero explícito != valor ausente.
"""

from dataclasses import dataclass, asdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from difflib import SequenceMatcher
import re
import unicodedata


Q4 = Decimal("0.0001")
Q2 = Decimal("0.01")


def _dec(value, default=None):
    if value is None or value == "":
        return default

    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _money(value, default=None):
    d = _dec(value, default)
    if d is None:
        return None
    return d.quantize(Q2, rounding=ROUND_HALF_UP)


def _qty(value, default=None):
    d = _dec(value, default)
    if d is None:
        return None
    return d.quantize(Q4, rounding=ROUND_HALF_UP)


def _text(value):
    value = str(value or "").strip().upper()

    value = "".join(
        c
        for c in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(c)
    )

    value = re.sub(r"[^A-Z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


UNIT_ALIASES = {
    "UD": "UD",
    "UDS": "UD",
    "UNIDAD": "UD",
    "UNIDADES": "UD",

    "M": "ML",
    "ML": "ML",
    "METRO": "ML",
    "METROS": "ML",

    "M2": "M2",
    "M²": "M2",

    "M3": "M3",
    "M³": "M3",

    "KG": "KG",
    "KGS": "KG",
    "KILO": "KG",
    "KILOS": "KG",

    "H": "H",
    "HR": "H",
    "HRS": "H",
    "HORA": "H",
    "HORAS": "H",

    "PORTE": "PORTE",
    "PERFIL": "PERFIL",
}


def normalizar_unidad(value):
    raw = _text(value).replace(" ", "")
    return UNIT_ALIASES.get(raw, raw)


def _first(item, *keys):
    for key in keys:
        if key in item:
            value = item.get(key)
            if value not in (None, ""):
                return value
    return None


def normalizar_linea_albaran(item):
    raw = (
        item.get("raw_data")
        if isinstance(item.get("raw_data"), dict)
        else {}
    )

    precio_raw = _first(
        item,
        "precio",
        "precio_unitario",
    )

    importe_raw = _first(
        item,
        "importe",
        "importe_linea",
    )

    precio = _dec(precio_raw, Decimal("0"))
    importe = _money(importe_raw, Decimal("0"))

    sin_valorar = bool(
        item.get("sin_valorar_albaran")
        or raw.get("albaran_linea_no_valorada")
        or (
            precio == Decimal("0")
            and importe == Decimal("0.00")
        )
    )

    return {
        "id": item.get("id") or item.get("albaran_linea_id"),
        "linea": item.get("linea"),
        "articulo_compra_id": item.get("articulo_compra_id"),

        "codigo": _text(
            _first(
                item,
                "codigo_proveedor",
                "codigo",
                "codigo_detectado",
                "referencia_proveedor",
            )
        ),

        "descripcion": str(
            _first(
                item,
                "descripcion",
                "descripcion_detectada",
                "nombre",
            )
            or ""
        ).strip(),

        "descripcion_norm": _text(
            _first(
                item,
                "descripcion",
                "descripcion_detectada",
                "nombre",
            )
        ),

        "cantidad": _qty(
            _first(
                item,
                "cantidad_compra",
                "cantidad",
            ),
            Decimal("0"),
        ),

        "unidad": normalizar_unidad(
            _first(
                item,
                "unidad_compra",
                "unidad",
            )
        ),

        "precio": precio.quantize(Q4),
        "importe": importe,
        "descuento": _dec(
            _first(
                item,
                "descuento",
                "descuento_porcentaje",
            ),
            Decimal("0"),
        ),

        "sin_valorar": sin_valorar,
    }


def normalizar_linea_factura(item):
    raw = (
        item.get("raw_data")
        if isinstance(item.get("raw_data"), dict)
        else {}
    )

    precio_present = any(
        key in item and item.get(key) not in (None, "")
        for key in (
            "precio",
            "precio_unitario",
            "precio_unitario_bruto",
        )
    )

    importe_present = any(
        key in item and item.get(key) not in (None, "")
        for key in (
            "importe",
            "importe_linea",
            "importe_calculado",
        )
    )

    descuento_present = any(
        key in item and item.get(key) not in (None, "")
        for key in (
            "descuento",
            "descuento_porcentaje",
            "descuento_detectado",
        )
    )

    if not descuento_present:
        descuento_present = (
            raw.get("descuento_porcentaje")
            not in (None, "")
        )

    precio = _dec(
        _first(
            item,
            "precio",
            "precio_unitario",
            "precio_unitario_bruto",
        ),
        None,
    )

    importe = _money(
        _first(
            item,
            "importe",
            "importe_linea",
            "importe_calculado",
        ),
        None,
    )

    descuento = _dec(
        _first(
            item,
            "descuento",
            "descuento_porcentaje",
            "descuento_detectado",
        ),
        None,
    )

    if descuento is None:
        descuento = _dec(
            raw.get("descuento_porcentaje"),
            None,
        )

    valoracion_explicita = bool(
        precio_present
        and importe_present
    )

    # 100 % con importe 0 sigue siendo valoración económica explícita.
    if (
        precio is not None
        and precio > 0
        and descuento == Decimal("100")
        and importe == Decimal("0.00")
    ):
        valoracion_explicita = True

    return {
        "linea": item.get("linea"),

        "codigo": _text(
            _first(
                item,
                "codigo_proveedor",
                "codigo",
                "codigo_detectado",
                "referencia_proveedor",
            )
        ),

        "descripcion": str(
            _first(
                item,
                "descripcion",
                "descripcion_detectada",
                "nombre",
            )
            or ""
        ).strip(),

        "descripcion_norm": _text(
            _first(
                item,
                "descripcion",
                "descripcion_detectada",
                "nombre",
            )
        ),

        "cantidad": _qty(
            _first(
                item,
                "cantidad",
                "cantidad_compra",
            ),
            None,
        ),

        "unidad": normalizar_unidad(
            _first(
                item,
                "unidad_compra",
                "unidad",
            )
        ),

        "precio": (
            precio.quantize(Q4)
            if precio is not None
            else None
        ),

        "importe": importe,

        "descuento": descuento,

        "valoracion_explicita": valoracion_explicita,

        "raw_data": raw,
    }


def similitud_descripcion(a, b):
    a = _text(a)
    b = _text(b)

    if not a or not b:
        return Decimal("0")

    return Decimal(
        str(
            round(
                SequenceMatcher(
                    None,
                    a,
                    b,
                ).ratio(),
                4,
            )
        )
    )


def cantidades_compatibles(a, b, tolerancia=Decimal("0.0001")):
    if a is None or b is None:
        return False

    return abs(a - b) <= tolerancia


def unidades_compatibles(a, b):
    a = normalizar_unidad(a)
    b = normalizar_unidad(b)

    if not a or not b:
        return False

    return a == b


def _score(alb, fac):
    score = 0
    razones = []

    if (
        alb["articulo_compra_id"]
        and fac.get("articulo_compra_id")
        and alb["articulo_compra_id"]
        == fac["articulo_compra_id"]
    ):
        score += 100
        razones.append("ARTICULO_EXACTO")

    if (
        alb["codigo"]
        and fac["codigo"]
        and alb["codigo"] == fac["codigo"]
    ):
        score += 80
        razones.append("CODIGO_EXACTO")

    if (
        alb["descripcion_norm"]
        and fac["descripcion_norm"]
        and alb["descripcion_norm"]
        == fac["descripcion_norm"]
    ):
        score += 70
        razones.append("DESCRIPCION_EXACTA")

    similarity = similitud_descripcion(
        alb["descripcion_norm"],
        fac["descripcion_norm"],
    )

    if similarity >= Decimal("0.90"):
        score += 40
        razones.append(
            f"DESCRIPCION_SIMILAR_{similarity}"
        )

    qty_ok = cantidades_compatibles(
        alb["cantidad"],
        fac["cantidad"],
    )

    unit_ok = unidades_compatibles(
        alb["unidad"],
        fac["unidad"],
    )

    if qty_ok:
        score += 15
        razones.append("CANTIDAD_COMPATIBLE")

    if unit_ok:
        score += 15
        razones.append("UNIDAD_COMPATIBLE")

    return score, razones, qty_ok, unit_ok


def reconciliar_lineas(
    lineas_albaran,
    lineas_factura,
):
    albaranes = [
        normalizar_linea_albaran(x)
        for x in lineas_albaran
    ]

    facturas = [
        normalizar_linea_factura(x)
        for x in lineas_factura
    ]

    usados = set()
    resultado = []

    for alb in albaranes:

        candidates = []

        for idx, fac in enumerate(facturas):

            if idx in usados:
                continue

            score, razones, qty_ok, unit_ok = _score(
                alb,
                fac,
            )

            if score:
                candidates.append(
                    (
                        score,
                        idx,
                        fac,
                        razones,
                        qty_ok,
                        unit_ok,
                    )
                )

        candidates.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        if not candidates:

            resultado.append(
                {
                    "albaran": alb,
                    "factura": None,
                    "estado_match": "SIN_MATCH",
                    "estado_valoracion": (
                        "PENDIENTE_VALORACION_FACTURA"
                        if alb["sin_valorar"]
                        else "VALORADA_EN_ALBARAN"
                    ),
                    "auto_aplicable": False,
                    "score": 0,
                    "razones": [],
                }
            )

            continue

        best = candidates[0]

        score, idx, fac, razones, qty_ok, unit_ok = best

        second_score = (
            candidates[1][0]
            if len(candidates) > 1
            else None
        )

        ambiguo = bool(
            second_score is not None
            and abs(score - second_score) <= 10
        )

        if ambiguo:

            resultado.append(
                {
                    "albaran": alb,
                    "factura": fac,
                    "estado_match": "MATCH_AMBIGUO",
                    "estado_valoracion": "PENDIENTE_REVISION",
                    "auto_aplicable": False,
                    "score": score,
                    "razones": razones,
                }
            )

            continue

        if score >= 70:
            estado_match = "MATCH_EXACTO"
        elif score >= 40:
            estado_match = "MATCH_PROPUESTO"
        else:
            estado_match = "SIN_MATCH"

        # VALORACION_DIFERIDA_STATUS_V2
        # Diferenciar:
        # - dato de unidad ausente;
        # - unidad realmente diferente;
        # - cantidad diferente;
        # - cantidad + unidad diferentes simultáneamente.
        alb_unit_known = bool(
            normalizar_unidad(
                alb.get("unidad")
            )
        )

        fac_unit_known = bool(
            normalizar_unidad(
                fac.get("unidad")
            )
        )

        if not fac["valoracion_explicita"]:

            estado_valoracion = (
                "PENDIENTE_VALORACION_FACTURA"
            )

            auto = False

        elif not alb_unit_known:

            estado_valoracion = (
                "UNIDAD_NO_INFORMADA_ALBARAN"
            )

            auto = False

        elif not fac_unit_known:

            estado_valoracion = (
                "UNIDAD_NO_INFORMADA_FACTURA"
            )

            auto = False

        elif not qty_ok and not unit_ok:

            estado_valoracion = (
                "DIFERENCIA_CANTIDAD_Y_UNIDAD"
            )

            auto = False

        elif not unit_ok:

            estado_valoracion = (
                "DIFERENCIA_UNIDAD"
            )

            auto = False

        elif not qty_ok:

            estado_valoracion = (
                "DIFERENCIA_CANTIDAD"
            )

            auto = False

        elif estado_match == "MATCH_EXACTO":

            estado_valoracion = (
                "VALORADA_EN_FACTURA"
            )

            auto = True

        else:

            estado_valoracion = (
                "PENDIENTE_REVISION"
            )

            auto = False

        if estado_match != "SIN_MATCH":
            usados.add(idx)

        resultado.append(
            {
                "albaran": alb,
                "factura": fac,
                "estado_match": estado_match,
                "estado_valoracion": estado_valoracion,
                "auto_aplicable": auto,
                "score": score,
                "razones": razones,
            }
        )

    return resultado


def resumen_reconciliacion(resultado):
    return {
        "total": len(resultado),

        "auto_aplicables": sum(
            1
            for x in resultado
            if x["auto_aplicable"]
        ),

        "pendientes": sum(
            1
            for x in resultado
            if not x["auto_aplicable"]
        ),

        "sin_valorar_albaran": sum(
            1
            for x in resultado
            if x["albaran"]["sin_valorar"]
        ),

        "valoradas_factura": sum(
            1
            for x in resultado
            if x["estado_valoracion"]
            == "VALORADA_EN_FACTURA"
        ),

        "diferencia_cantidad": sum(
            1
            for x in resultado
            if x["estado_valoracion"]
            in {
                "DIFERENCIA_CANTIDAD",
                "DIFERENCIA_CANTIDAD_Y_UNIDAD",
            }
        ),

        "diferencia_unidad": sum(
            1
            for x in resultado
            if x["estado_valoracion"]
            in {
                "DIFERENCIA_UNIDAD",
                "DIFERENCIA_CANTIDAD_Y_UNIDAD",
            }
        ),

        "diferencia_cantidad_y_unidad": sum(
            1
            for x in resultado
            if x["estado_valoracion"]
            == "DIFERENCIA_CANTIDAD_Y_UNIDAD"
        ),

        "unidad_no_informada": sum(
            1
            for x in resultado
            if x["estado_valoracion"]
            in {
                "UNIDAD_NO_INFORMADA_ALBARAN",
                "UNIDAD_NO_INFORMADA_FACTURA",
            }
        ),
    }
