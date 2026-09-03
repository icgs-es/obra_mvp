"""
PORTAL INTASA · Catálogo canónico de unidades V1.

Normaliza variantes léxicas, pero nunca convierte cantidades
entre unidades físicas o comerciales distintas.
"""

from __future__ import annotations

import re
import unicodedata


UNIT_DEFINITIONS = (
    ("UD", "Unidad (UD)"),
    ("H", "Hora (h)"),
    ("DIA", "Día"),
    ("MES", "Mes"),
    ("SERVICIO", "Servicio"),
    ("M", "Metro (m)"),
    ("ML", "Metro lineal (ML)"),
    ("M2", "Metro cuadrado (m²)"),
    ("M3", "Metro cúbico (m³)"),
    ("L", "Litro (l)"),
    ("KG", "Kilogramo (kg)"),
    ("TN", "Tonelada (t)"),
    ("CAJA", "Caja"),
    ("SACO", "Saco"),
    ("SACA", "Saca"),
    ("BOLSA", "Bolsa"),
    ("PAQUETE", "Paquete"),
    ("PACK", "Pack"),
    ("PALET", "Palé"),
    ("ROLLO", "Rollo"),
    ("BOTE", "Bote"),
    ("CUBA", "Cuba"),
    ("PERFIL", "Perfil"),
    ("PLACA", "Placa"),
    ("PORTE", "Porte"),
    ("PA", "Partida alzada (PA)"),
)

CANONICAL_CODES = {
    code
    for code, _label in UNIT_DEFINITIONS
}


def _token(value):
    raw = str(
        value or ""
    ).strip()

    if not raw:
        return ""

    raw = (
        raw
        .replace("²", "2")
        .replace("³", "3")
    )

    normalized = unicodedata.normalize(
        "NFKD",
        raw,
    )

    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(
            character
        )
    )

    normalized = normalized.upper()

    return re.sub(
        r"[^A-Z0-9]+",
        "",
        normalized,
    )


ALIASES = {
    # Unidad.
    "U": "UD",
    "UD": "UD",
    "UDS": "UD",
    "UN": "UD",
    "UND": "UD",
    "UNDS": "UD",
    "UNID": "UD",
    "UNIDS": "UD",
    "UNIDAD": "UD",
    "UNIDADES": "UD",

    # Tiempo.
    "H": "H",
    "HR": "H",
    "HRS": "H",
    "HORA": "H",
    "HORAS": "H",

    "DIA": "DIA",
    "DIAS": "DIA",

    "MES": "MES",
    "MESES": "MES",
    "MENSUAL": "MES",
    "MENSUALIDAD": "MES",
    "MENSUALIDADES": "MES",

    "SERVICIO": "SERVICIO",
    "SERVICIOS": "SERVICIO",

    # Longitud, superficie y volumen.
    "M": "M",
    "MT": "M",
    "MTS": "M",
    "METRO": "M",
    "METROS": "M",

    "ML": "ML",
    "METROLINEAL": "ML",
    "METROSLINEALES": "ML",

    "M2": "M2",
    "METROCUADRADO": "M2",
    "METROSCUADRADOS": "M2",

    "M3": "M3",
    "METROCUBICO": "M3",
    "METROSCUBICOS": "M3",

    # Capacidad y masa.
    "L": "L",
    "LT": "L",
    "LTS": "L",
    "LTR": "L",
    "LTRS": "L",
    "LITRO": "L",
    "LITROS": "L",

    "KG": "KG",
    "KGS": "KG",
    "KILO": "KG",
    "KILOS": "KG",
    "KILOGRAMO": "KG",
    "KILOGRAMOS": "KG",

    "T": "TN",
    "TN": "TN",
    "TNS": "TN",
    "TON": "TN",
    "TONEL": "TN",
    "TONELADA": "TN",
    "TONELADAS": "TN",

    # Formatos comerciales.
    "CAJA": "CAJA",
    "CAJAS": "CAJA",

    "SACO": "SACO",
    "SACOS": "SACO",

    "SACA": "SACA",
    "SACAS": "SACA",

    "BOLSA": "BOLSA",
    "BOLSAS": "BOLSA",

    "PAQUETE": "PAQUETE",
    "PAQUETES": "PAQUETE",

    "PACK": "PACK",
    "PACKS": "PACK",

    "PALET": "PALET",
    "PALETS": "PALET",
    "PALE": "PALET",
    "PALES": "PALET",

    "ROLLO": "ROLLO",
    "ROLLOS": "ROLLO",

    "BOTE": "BOTE",
    "BOTES": "BOTE",

    "CUBA": "CUBA",
    "CUBAS": "CUBA",

    "PERFIL": "PERFIL",
    "PERFILES": "PERFIL",

    "PLACA": "PLACA",
    "PLACAS": "PLACA",

    "PORTE": "PORTE",
    "PORTES": "PORTE",

    "PA": "PA",
}


def normalize_unit(
    value,
    *,
    preserve_unknown=True,
):
    """
    Devuelve el código canónico de la unidad.

    No realiza conversiones entre unidades diferentes.
    """

    raw = str(
        value or ""
    ).strip()

    if not raw:
        return ""

    token = _token(raw)

    if token in ALIASES:
        return ALIASES[token]

    if token in CANONICAL_CODES:
        return token

    if preserve_unknown:
        return raw.upper()

    return ""


def unit_choices(
    *,
    current_value="",
    include_blank=True,
):
    choices = []

    if include_blank:
        choices.append(
            (
                "",
                "Selecciona unidad...",
            )
        )

    choices.extend(
        UNIT_DEFINITIONS
    )

    current = normalize_unit(
        current_value
    )

    known_values = {
        value
        for value, _label in choices
    }

    if (
        current
        and current not in known_values
    ):
        choices.append(
            (
                current,
                f"{current} · valor histórico",
            )
        )

    return choices


def normalize_nature(
    value,
    *,
    default="MATERIAL",
):
    """
    FACTURA_ARTICULO_NATURALEZAS_MINIMAL_V1_1

    Naturalezas canónicas:
    MATERIAL
    SERVICIO
    HERRAMIENTA
    MAQUINARIA
    PORTES
    """

    token = _token(value)

    aliases = {
        "MATERIAL": "MATERIAL",
        "MATERIALES": "MATERIAL",
        "ARTICULO": "MATERIAL",
        "ARTICULOS": "MATERIAL",
        "RECURSO": "MATERIAL",
        "RECURSOS": "MATERIAL",

        "SERVICIO": "SERVICIO",
        "SERVICIOS": "SERVICIO",

        "HERRAMIENTA": "HERRAMIENTA",
        "HERRAMIENTAS": "HERRAMIENTA",

        "MAQUINARIA": "MAQUINARIA",
        "MAQUINARIAS": "MAQUINARIA",

        "PORTE": "PORTES",
        "PORTES": "PORTES",
    }

    if token in aliases:
        return aliases[token]

    return default




def is_same_unit(
    left,
    right,
):
    return (
        normalize_unit(left)
        == normalize_unit(right)
    )
