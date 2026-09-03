# FACTURA_NATURALEZA_V1

import re
import unicodedata

from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_HALF_UP,
)


CENT = Decimal("0.01")


def _norm_text(value):
    text = unicodedata.normalize(
        "NFKD",
        str(value or "").upper(),
    )

    return "".join(
        ch
        for ch in text
        if not unicodedata.combining(ch)
    )


def _money(value):
    if value in (None, ""):
        return None

    raw = (
        str(value)
        .strip()
        .replace("€", "")
        .replace("EUR", "")
        .replace(" ", "")
    )

    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = (
                raw
                .replace(".", "")
                .replace(",", ".")
            )
        else:
            raw = raw.replace(",", "")

    elif "," in raw:
        raw = raw.replace(",", ".")

    try:
        return Decimal(raw).quantize(
            CENT,
            rounding=ROUND_HALF_UP,
        )
    except (
        InvalidOperation,
        ValueError,
        TypeError,
    ):
        return None


def _fmt(value):
    if value is None:
        return ""

    return (
        f"{value.quantize(CENT, rounding=ROUND_HALF_UP):.2f}"
    )


def _first(data, *keys):
    if not isinstance(data, dict):
        return None

    for key in keys:
        value = data.get(key)

        if value not in (None, ""):
            return value

    return None


def _flatten_strings(value, depth=0):
    if depth > 4:
        return []

    if isinstance(value, str):
        return [value]

    if isinstance(value, dict):
        result = []

        for key, item in value.items():
            if key in {
                "text",
                "raw_extract",
                "raw_data",
                "parser",
                "parser_key",
                "tipo_documento",
                "tipo",
                "subtipo",
                "source",
            }:
                result.extend(
                    _flatten_strings(
                        item,
                        depth + 1,
                    )
                )

            elif isinstance(
                item,
                (
                    dict,
                    list,
                    tuple,
                ),
            ):
                result.extend(
                    _flatten_strings(
                        item,
                        depth + 1,
                    )
                )

        return result

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        result = []

        for item in value:
            result.extend(
                _flatten_strings(
                    item,
                    depth + 1,
                )
            )

        return result

    return []


def _sync_amounts(
    target,
    base,
    iva,
    total,
):
    if not isinstance(target, dict):
        return

    if base is not None:
        for key in (
            "base",
            "base_imponible",
            "importe_base_imponible",
        ):
            target[key] = _fmt(base)

    if iva is not None:
        for key in (
            "iva",
            "importe_iva",
        ):
            target[key] = _fmt(iva)

    if total is not None:
        for key in (
            "total",
            "total_factura",
            "importe_factura",
        ):
            target[key] = _fmt(total)


def _sync_number(
    target,
    number,
):
    if (
        not isinstance(target, dict)
        or not number
    ):
        return

    for key in (
        "numero",
        "numero_documento",
        "numero_factura",
        "num_factura",
        "num_factura_proveedor",
        "numero_factura_proveedor",
    ):
        target[key] = number


def normalizar_factura_extraida_v1(
    extracted,
    initial=None,
    original_name="",
):
    """
    Política canónica PORTAL INTASA.

    NORMAL:
      conserva el signo del documento.

    RECTIFICATIVA / OTRA:
      conserva el signo del documento.

    RECTIFICATIVA / ABONO:
      el proveedor puede imprimir importes positivos,
      pero el efecto económico INTASA es negativo en:
        - base;
        - IVA;
        - total.

    Los importes documentales originales se conservan
    en factura_naturaleza_v1.documento_importes.
    """

    out = dict(extracted or {})

    init = (
        dict(initial or {})
        if isinstance(initial, dict)
        else initial
    )

    # FACTURA_NATURALEZA_FILENAME_SAFE_V1
    #
    # El nombre del fichero sirve como señal de naturaleza
    # ("Abono ...pdf"), pero nunca como fuente del número
    # fiscal/documental. Evita interpretar ".PDF" como parte
    # del número de abono.
    content_probe = _norm_text(
        "\n".join(
            _flatten_strings(out)
        )
    )

    filename_probe = _norm_text(
        str(original_name or "")
    )

    probe = "\n".join(
        (
            content_probe,
            filename_probe,
        )
    )

    # ---------------------------------------------------------
    # ABONO explícito
    # ---------------------------------------------------------

    abono_match = re.search(
        (
            r"\bABONO"
            r"(?:\s+N[Oº°.]*)?"
            r"\s*[:#-]?\s*"
            r"(AB[A-Z0-9][A-Z0-9./_-]*)"
        ),
        content_probe,
    )

    numero_abono = (
        abono_match
        .group(1)
        .strip(" .,:;-")
        if abono_match
        else ""
    )

    raw_signal_abono = any(
        token in probe
        for token in (
            "FACTURA_ABONO",
            "ABONO_DEVOLUCION",
            "NOTA DE CREDITO",
            "CREDIT NOTE",
        )
    )

    es_abono = bool(
        abono_match
        or raw_signal_abono
        or "ABONO" in filename_probe
    )

    # ---------------------------------------------------------
    # RECTIFICATIVA genérica
    # ---------------------------------------------------------

    es_rectificativa = (
        es_abono
        or any(
            token in probe
            for token in (
                "FACTURA RECTIFICATIVA",
                "RECTIFICACION DE",
                "RECTIFICACION A",
                "RECTIFICA A",
            )
        )
    )

    # ---------------------------------------------------------
    # FACTURA RECTIFICADA
    # ---------------------------------------------------------

    ref_match = re.search(
        (
            r"CORRESPONDE\s+A\s+LA\s+FACTURA"
            r"\s*[-:]*\s*"
            r"([A-Z0-9][A-Z0-9./_-]{3,})"
        ),
        probe,
    )

    if not ref_match:
        ref_match = re.search(
            (
                r"RECTIFICACION\s+(?:DE|A)\s+"
                r"(?:LA\s+FACTURA\s+)?"
                r"([A-Z0-9][A-Z0-9./_-]{3,})"
            ),
            probe,
        )

    numero_rectificada = (
        ref_match
        .group(1)
        .strip(" .,:;-")
        if ref_match
        else ""
    )

    # ---------------------------------------------------------
    # NÚMERO DEL DOCUMENTO
    # ---------------------------------------------------------

    numero_inicial = ""

    if isinstance(init, dict):
        numero_inicial = str(
            _first(
                init,
                "num_factura_proveedor",
                "numero_documento",
                "numero_factura",
                "numero",
            )
            or ""
        ).strip()

    numero_actual = str(
        _first(
            out,
            "num_factura_proveedor",
            "numero_documento",
            "numero_factura",
            "numero",
        )
        or ""
    ).strip()

    if es_abono:
        # Para un abono, nunca reutilizar como número propio
        # el número de la factura rectificada.
        #
        # Prioridad:
        #   1. número AB detectado en contenido OCR;
        #   2. número AB revisado/introducido por el usuario;
        #   3. vacío: el formulario mantiene el valor humano.
        numero_documento = (
            numero_abono
            or (
                numero_inicial
                if numero_inicial.upper().startswith("AB")
                else ""
            )
        )
    else:
        numero_documento = (
            numero_actual
            or numero_inicial
        )

    # ---------------------------------------------------------
    # IMPORTES
    # ---------------------------------------------------------

    base_src = _money(
        _first(
            out,
            "importe_base_imponible",
            "base_imponible",
            "base",
        )
    )

    iva_src = _money(
        _first(
            out,
            "importe_iva",
            "iva",
        )
    )

    total_src = _money(
        _first(
            out,
            "importe_factura",
            "total_factura",
            "total",
        )
    )

    # Valor documental:
    # conservar magnitud positiva del PDF.
    base_doc = (
        abs(base_src)
        if base_src is not None
        else None
    )

    iva_doc = (
        abs(iva_src)
        if iva_src is not None
        else None
    )

    total_doc = (
        abs(total_src)
        if total_src is not None
        else None
    )

    # Valor económico.
    if es_abono:
        base_econ = (
            -abs(base_src)
            if base_src is not None
            else None
        )

        iva_econ = (
            -abs(iva_src)
            if iva_src is not None
            else None
        )

        total_econ = (
            -abs(total_src)
            if total_src is not None
            else None
        )

    else:
        base_econ = base_src
        iva_econ = iva_src
        total_econ = total_src

    tipo_factura = (
        "RECTIFICATIVA"
        if es_rectificativa
        else "NORMAL"
    )

    subtipo = (
        "ABONO"
        if es_abono
        else (
            "OTRA"
            if es_rectificativa
            else ""
        )
    )

    metadata = {
        "version": (
            "FACTURA_NATURALEZA_V1"
        ),
        "tipo_factura": tipo_factura,
        "subtipo_rectificativa": subtipo,
        "numero_documento": (
            numero_documento
        ),
        "numero_factura_rectificada": (
            numero_rectificada
        ),
        "signo_economico": (
            "NEGATIVO"
            if es_abono
            else "SEGUN_DOCUMENTO"
        ),
        "documento_importes": {
            "base": _fmt(base_doc),
            "iva": _fmt(iva_doc),
            "total": _fmt(total_doc),
        },
        "efecto_economico": {
            "base": _fmt(base_econ),
            "iva": _fmt(iva_econ),
            "total": _fmt(total_econ),
        },
        "deteccion": {
            "abono_explicito": bool(
                abono_match
            ),
            "abono_por_senal_parser": bool(
                raw_signal_abono
            ),
            "rectificativa": bool(
                es_rectificativa
            ),
        },
    }

    _sync_amounts(
        out,
        base_econ,
        iva_econ,
        total_econ,
    )

    if numero_abono:
        _sync_number(
            out,
            numero_abono,
        )

    raw_data = out.get("raw_data")

    if not isinstance(
        raw_data,
        dict,
    ):
        raw_data = {}
    else:
        raw_data = dict(raw_data)

    raw_data[
        "factura_naturaleza_v1"
    ] = metadata

    out["raw_data"] = raw_data
    out["factura_naturaleza_v1"] = (
        metadata
    )

    if isinstance(init, dict):
        _sync_amounts(
            init,
            base_econ,
            iva_econ,
            total_econ,
        )

        if numero_abono:
            init[
                "num_factura_proveedor"
            ] = numero_abono

        init[
            "factura_naturaleza_v1"
        ] = metadata

    return (
        out,
        init,
        metadata,
    )
