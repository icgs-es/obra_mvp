"""
PORTAL INTASA
ALBARAN_TEMPLATE_ROUTER_CANONICAL_V1

Los parser_key registrados quedan aislados de la cadena histórica.

Los no registrados continúan por pdf_extractor.py sin cambios.
"""

# ALBARAN_TEMPLATE_ROUTER_CANONICAL_V1

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from difflib import SequenceMatcher
import re

from apps.gestion.services.document_text import (
    extract_document_text_v1,
)


def _dec_v1(value, default=None):
    raw = str(
        value
        if value is not None
        else ""
    ).strip()

    raw = (
        raw
        .replace("€", "")
        .replace("%", "")
        .replace("\xa0", "")
        .replace(" ", "")
    )

    raw = re.sub(
        r"[^0-9,.\-]",
        "",
        raw,
    )

    if not raw:
        return default

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
        return Decimal(raw)

    except (
        InvalidOperation,
        ValueError,
    ):
        return default


def _fmt_v1(
    value,
    quant="0.01",
):
    dec = (
        value
        if isinstance(value, Decimal)
        else _dec_v1(
            value,
            Decimal("0"),
        )
    )

    return str(
        dec.quantize(
            Decimal(quant),
            rounding=ROUND_HALF_UP,
        )
    )


def _word_similarity_v1(
    value,
    expected,
):
    value = re.sub(
        r"[^a-z]",
        "",
        str(value or "").lower(),
    )

    expected = re.sub(
        r"[^a-z]",
        "",
        str(expected or "").lower(),
    )

    if not value or not expected:
        return 0.0

    return SequenceMatcher(
        None,
        value,
        expected,
    ).ratio()


def _find_labeled_token_v1(
    text,
    *,
    label,
):
    for raw in str(text or "").splitlines():

        parts = raw.split()

        if not parts:
            continue

        for idx, token in enumerate(
            parts[:4]
        ):
            if (
                _word_similarity_v1(
                    token,
                    label,
                )
                < 0.62
            ):
                continue

            for candidate in parts[
                idx + 1:
                idx + 6
            ]:
                cleaned = re.sub(
                    r"[^A-Z0-9\-]",
                    "",
                    candidate.upper(),
                )

                if len(cleaned) >= 5:
                    return cleaned

    return ""


def _normalize_document_number_v1(
    value,
    *,
    expected_prefix="",
    expected_digits=None,
):
    raw = re.sub(
        r"[^A-Z0-9]",
        "",
        str(value or "").upper(),
    )

    prefix = re.sub(
        r"[^A-Z]",
        "",
        str(
            expected_prefix
            or ""
        ).upper(),
    )

    if prefix and raw.startswith(prefix):
        digits = re.sub(
            r"\D",
            "",
            raw[len(prefix):],
        )
    else:
        digits = re.sub(
            r"\D",
            "",
            raw,
        )

    if expected_digits:

        expected_digits = int(
            expected_digits
        )

        # Corrección OCR genérica:
        # si sobra exactamente un carácter y existen
        # dígitos consecutivos duplicados, quitar uno.
        while len(digits) > expected_digits:

            if (
                len(digits)
                != expected_digits + 1
            ):
                break

            removed = False

            for idx in range(
                1,
                len(digits),
            ):
                if (
                    digits[idx]
                    == digits[idx - 1]
                ):
                    digits = (
                        digits[:idx]
                        + digits[idx + 1:]
                    )
                    removed = True
                    break

            if not removed:
                break

        if len(digits) != expected_digits:
            return ""

    if not digits:
        return ""

    return (
        prefix + digits
        if prefix
        else digits
    )


def _find_date_v1(text):
    for raw in str(text or "").splitlines():

        parts = raw.split()

        if not parts:
            continue

        looks_date_line = any(
            _word_similarity_v1(
                token,
                "fecha",
            ) >= 0.62
            for token in parts[:4]
        )

        if not looks_date_line:
            continue

        match = re.search(
            r"\b"
            r"(?P<d>\d{1,2})"
            r"[-/]"
            r"(?P<m>\d{1,2})"
            r"[-/]"
            r"(?P<y>\d{2,4})"
            r"\b",
            raw,
        )

        if not match:
            continue

        day = int(match.group("d"))
        month = int(match.group("m"))
        year = int(match.group("y"))

        if year < 100:
            year += 2000

        return {
            "fecha": (
                f"{day:02d}/"
                f"{month:02d}/"
                f"{year:04d}"
            ),
            "fecha_iso": (
                f"{year:04d}-"
                f"{month:02d}-"
                f"{day:02d}"
            ),
        }

    return {
        "fecha": "",
        "fecha_iso": "",
    }


def _fiscal_totals_v1(text):
    """
    Resolver genérico de bloque fiscal.

    Selecciona Base, IVA y Total mediante:
        base + iva == total

    y favorece tipos IVA habituales.

    No depende del proveedor.
    """

    lines = str(text or "").splitlines()

    start = None

    for idx, raw in enumerate(lines):

        upper = raw.upper()

        hits = sum(
            token in upper
            for token in (
                "BRUTO",
                "BASE",
                "CUOTA",
                "IVA",
                "TOTAL",
                "DESCUENTO",
            )
        )

        if hits >= 2:
            start = idx
            break

    if start is None:
        return {}

    region = "\n".join(
        lines[start:start + 14]
    )

    values = []

    for match in re.finditer(
        r"(?<!\d)"
        r"\d+(?:[.,]\d{2})"
        r"(?!\d)",
        region,
    ):

        # Excluir porcentajes.
        tail = region[
            match.end():
            match.end() + 3
        ]

        if "%" in tail:
            continue

        value = _dec_v1(
            match.group(0)
        )

        if (
            value is not None
            and Decimal("0") < value
            < Decimal("100000000")
        ):
            values.append(value)

    if len(values) < 3:
        return {}

    vat_rates = (
        Decimal("4"),
        Decimal("10"),
        Decimal("21"),
    )

    best = None

    for bi, base in enumerate(values):

        for ii, iva in enumerate(values):

            if ii == bi:
                continue

            if iva <= 0 or iva >= base:
                continue

            for ti, total in enumerate(values):

                if ti in (bi, ii):
                    continue

                equation_error = abs(
                    base + iva - total
                )

                if (
                    equation_error
                    > Decimal("0.03")
                ):
                    continue

                rate = (
                    iva
                    / base
                    * Decimal("100")
                )

                rate_error = min(
                    abs(rate - expected)
                    for expected in vat_rates
                )

                score = (
                    equation_error
                    * Decimal("10000")
                    + rate_error
                )

                if total <= base:
                    score += Decimal("100")

                candidate = {
                    "score": score,
                    "base": base,
                    "iva": iva,
                    "total": total,
                    "iva_pct": rate,
                }

                if (
                    best is None
                    or candidate["score"]
                    < best["score"]
                ):
                    best = candidate

    if not best:
        return {}

    result = {
        "base_imponible": _fmt_v1(
            best["base"]
        ),
        "iva": _fmt_v1(
            best["iva"]
        ),
        "total": _fmt_v1(
            best["total"]
        ),
        "iva_porcentaje": _fmt_v1(
            best["iva_pct"]
        ),
    }

    # Si además existen bruto/descuento que cuadran,
    # conservarlos como evidencia.
    for bruto in values:

        for descuento in values:

            if bruto == descuento:
                continue

            if abs(
                bruto
                - descuento
                - best["base"]
            ) <= Decimal("0.03"):

                result["bruto"] = (
                    _fmt_v1(bruto)
                )

                result["descuento"] = (
                    _fmt_v1(descuento)
                )

                return result

    return result


def _clean_description_v1(value):
    desc = re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip(" -|:;")

    # Ruido OCR corto al final de una descripción
    # inmediatamente antes de las columnas numéricas.
    desc = re.sub(
        r"\s+\(\s*1"
        r"(?:\s+[A-Za-z0-9]{1,2}){1,3}"
        r"\s*$",
        "",
        desc,
    )

    desc = re.sub(
        r"\s+[A-Za-z]{1,2}\s*$",
        "",
        desc,
    )

    return desc.strip(
        " -|:;,"
    )


def _valued_table_lines_v1(
    text,
    *,
    parser_key,
):
    """
    Parser tabular genérico:

        código
        descripción
        cantidad
        unidad
        precio
        descuento
        importe

    Validación:
        cantidad × precio × (1-dto/100) == importe
    """

    result = {
        "parser": parser_key,
        "parser_key": parser_key,
        "lineas": [],
        "total_lineas": "0.00",
        "warnings": [],
        "errors": [],
        "debug": {
            "candidate_lines": [],
            "discarded_lines": [],
        },
    }

    code_re = re.compile(
        r"^(?P<code>"
        r"[A-Z0-9]"
        r"[A-Z0-9._/\-]{3,20}"
        r")\s+"
        r"(?P<body>.+)$",
        re.I,
    )

    unit_re = re.compile(
        r"\b"
        r"(UN|UND|UD|U|KG|M2|M3|ML|M|"
        r"PAQ|PZA|PZAS|SACO|CAJA|BOTE)"
        r"\b",
        re.I,
    )

    number_re = re.compile(
        r"-?\d+"
        r"(?:[.,]\d{1,4})?"
    )

    parsed = []

    for raw_line in str(text or "").splitlines():

        clean = str(
            raw_line
            or ""
        ).strip()

        clean = re.sub(
            r"^[^A-Z0-9]+",
            "",
            clean,
            flags=re.I,
        )

        match = code_re.match(clean)

        if not match:
            continue

        code = (
            match.group("code")
            .strip()
            .upper()
        )

        body = match.group("body")

        unit_matches = list(
            unit_re.finditer(body)
        )

        if not unit_matches:
            continue

        unit_match = unit_matches[-1]

        before_unit = body[
            :unit_match.start()
        ]

        after_unit = body[
            unit_match.end():
        ]

        before_numbers = list(
            number_re.finditer(
                before_unit
            )
        )

        after_numbers = list(
            number_re.finditer(
                after_unit
            )
        )

        if (
            not before_numbers
            or len(after_numbers) < 2
        ):
            continue

        qty_match = before_numbers[-1]

        cantidad = _dec_v1(
            qty_match.group(0)
        )

        descripcion = (
            before_unit[
                :qty_match.start()
            ]
        )

        descripcion = (
            _clean_description_v1(
                descripcion
            )
        )

        precio = _dec_v1(
            after_numbers[0].group(0)
        )

        if len(after_numbers) >= 3:
            descuento = _dec_v1(
                after_numbers[1].group(0),
                Decimal("0"),
            )

            importe = _dec_v1(
                after_numbers[2].group(0)
            )

        else:
            descuento = Decimal("0.00")

            importe = _dec_v1(
                after_numbers[1].group(0)
            )

        if (
            cantidad is None
            or precio is None
            or importe is None
        ):
            continue

        if (
            cantidad <= 0
            or precio < 0
            or importe < 0
            or descuento < 0
            or descuento >= 100
        ):
            continue

        esperado = (
            cantidad
            * precio
            * (
                Decimal("100")
                - descuento
            )
            / Decimal("100")
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        error = abs(
            esperado - importe
        )

        if error > Decimal("0.03"):
            result["debug"][
                "discarded_lines"
            ].append({
                "raw": raw_line,
                "reason": "math_mismatch",
                "expected": str(esperado),
                "amount": str(importe),
            })

            continue

        if len(descripcion) < 3:
            continue

        item = {
            "linea": len(parsed) + 1,
            "codigo": code,
            "cod_articulo": code,
            "codigo_detectado": code,
            "codigo_proveedor": code,
            "descripcion": descripcion,
            "cantidad": _fmt_v1(
                cantidad,
                "0.0000",
            ),
            "cantidad_input": _fmt_v1(
                cantidad,
                "0.0000",
            ),
            "unidad": (
                unit_match.group(1)
                .upper()
            ),
            "unidad_compra": (
                unit_match.group(1)
                .upper()
            ),
            "precio": _fmt_v1(
                precio,
                "0.0000",
            ),
            "precio_unitario": _fmt_v1(
                precio,
                "0.0000",
            ),
            "precio_detectado": _fmt_v1(
                precio,
                "0.0000",
            ),
            "precio_input": _fmt_v1(
                precio,
                "0.0000",
            ),
            "descuento": _fmt_v1(
                descuento
            ),
            "descuento_input": _fmt_v1(
                descuento
            ),
            "importe": _fmt_v1(
                importe
            ),
            "importe_linea": _fmt_v1(
                importe
            ),
            "importe_detectado": _fmt_v1(
                importe
            ),
            "importe_calculado": _fmt_v1(
                importe
            ),
            "importe_input": _fmt_v1(
                importe
            ),
            "math_error": _fmt_v1(
                error
            ),
            "raw": raw_line,
            "raw_line": raw_line,
            "source": (
                "albaran_template_router_"
                "canonical_v1"
            ),
            "source_parser": parser_key,
        }

        # Firma para reconciliar pequeñas mutaciones
        # OCR del mismo código repetido.
        desc_words = re.findall(
            r"[A-Z0-9]+",
            descripcion.upper(),
        )

        item["_signature"] = (
            tuple(desc_words[:5]),
            item["cantidad"],
            item["precio"],
            item["descuento"],
            item["importe"],
        )

        parsed.append(item)

        result["debug"][
            "candidate_lines"
        ].append(raw_line)

    # Reconciliación por mayoría:
    # si varias filas económicamente idénticas tienen
    # una variante OCR de código, gana la más frecuente.
    grouped = defaultdict(list)

    for item in parsed:
        grouped[
            item["_signature"]
        ].append(item)

    for items in grouped.values():

        if len(items) < 2:
            continue

        counts = Counter(
            item["codigo"]
            for item in items
        )

        canonical_code, count = (
            counts.most_common(1)[0]
        )

        if count < 2:
            continue

        for item in items:
            item["codigo"] = canonical_code
            item["cod_articulo"] = canonical_code
            item["codigo_detectado"] = canonical_code
            item["codigo_proveedor"] = canonical_code

    total = Decimal("0.00")

    for idx, item in enumerate(
        parsed,
        1,
    ):
        item.pop(
            "_signature",
            None,
        )

        item["linea"] = idx

        total += _dec_v1(
            item["importe"],
            Decimal("0"),
        )

    result["lineas"] = parsed

    result["total_lineas"] = (
        _fmt_v1(total)
    )

    if not parsed:
        result["warnings"].append(
            "No se detectaron filas valoradas "
            "con validación matemática."
        )

    return result


# =====================================================================
# CANO · primer formato registrado
#
# Lo específico queda en configuración del formato,
# no en el extractor documental ni en los entrypoints globales.
# =====================================================================

def _cano_header_v1(
    text,
    *,
    config=None,
):
    config = (
        config
        if isinstance(config, dict)
        else {}
    )

    number_raw = _find_labeled_token_v1(
        text,
        label="albaran",
    )

    numero = (
        _normalize_document_number_v1(
            number_raw,
            expected_prefix=(
                config.get(
                    "document_number_prefix"
                )
                or "K"
            ),
            expected_digits=(
                config.get(
                    "document_number_digits"
                )
                or 7
            ),
        )
    )

    fecha = _find_date_v1(text)
    fiscal = _fiscal_totals_v1(text)

    result = {
        "parser_key": (
            "cano_albaran_valorado_v1"
        ),
        "numero_documento": numero,
        "num_albaran_proveedor": numero,
        "fecha": fecha["fecha"],
        "fecha_iso": fecha["fecha_iso"],
        "base_imponible": fiscal.get(
            "base_imponible",
            "",
        ),
        "iva": fiscal.get("iva", ""),
        "total": fiscal.get("total", ""),
        "importe_albaran": fiscal.get(
            "total",
            "",
        ),
        "iva_porcentaje": fiscal.get(
            "iva_porcentaje",
            "",
        ),
        "bruto": fiscal.get(
            "bruto",
            "",
        ),
        "descuento": fiscal.get(
            "descuento",
            "",
        ),
    }

    return result


def _cano_lines_v1(
    text,
    *,
    config=None,
):
    return _valued_table_lines_v1(
        text,
        parser_key=(
            "cano_albaran_valorado_v1"
        ),
    )


ALBARAN_TEMPLATE_PARSER_REGISTRY_V1 = {
    "cano_albaran_valorado_v1": {
        "header": _cano_header_v1,
        "lines": _cano_lines_v1,
        "config": {
            "document_number_prefix": "K",
            "document_number_digits": 7,
        },
    },
}


def get_registered_albaran_parser_v1(
    parser_key,
):
    return (
        ALBARAN_TEMPLATE_PARSER_REGISTRY_V1
        .get(
            str(
                parser_key
                or ""
            ).strip().lower()
        )
    )


def _parser_config_v1(
    spec,
    plantilla=None,
):
    config = dict(
        spec.get("config")
        or {}
    )

    if (
        plantilla is not None
        and isinstance(
            getattr(
                plantilla,
                "config_json",
                None,
            ),
            dict,
        )
    ):
        config.update(
            plantilla.config_json
        )

    return config


def apply_albaran_template_router_v1(
    pdf_path,
    *,
    parser_key,
    legacy_text_result=None,
    plantilla=None,
    max_pages=3,
):
    """
    Devuelve None para parser_key no migrados.

    Así los proveedores actuales conservan
    exactamente su comportamiento legacy.
    """

    spec = get_registered_albaran_parser_v1(
        parser_key
    )

    if not spec:
        return None

    text_result = (
        extract_document_text_v1(
            pdf_path,
            legacy_result=legacy_text_result,
            max_pages=max_pages,
        )
    )

    text = text_result.get(
        "text",
        "",
    )

    config = _parser_config_v1(
        spec,
        plantilla=plantilla,
    )

    header = spec["header"](
        text,
        config=config,
    )

    lines = spec["lines"](
        text,
        config=config,
    )

    base = _dec_v1(
        header.get("base_imponible")
    )

    iva = _dec_v1(
        header.get("iva")
    )

    total = _dec_v1(
        header.get("total")
    )

    line_sum = _dec_v1(
        lines.get("total_lineas")
    )

    header_math_ok = bool(
        base is not None
        and iva is not None
        and total is not None
        and abs(
            base + iva - total
        ) <= Decimal("0.03")
    )

    lines_match_base = bool(
        base is not None
        and line_sum is not None
        and abs(
            base - line_sum
        ) <= Decimal("0.03")
    )

    validation = {
        "parser_key": parser_key,
        "text_method": text_result.get(
            "method",
        ),
        "ocr_used": text_result.get(
            "ocr_used",
        ),
        "number_ok": bool(
            header.get(
                "numero_documento"
            )
        ),
        "date_ok": bool(
            header.get("fecha_iso")
        ),
        "header_math_ok": (
            header_math_ok
        ),
        "lines_match_base": (
            lines_match_base
        ),
        "line_count": len(
            lines.get("lineas")
            or []
        ),
        "line_sum": lines.get(
            "total_lineas"
        ),
    }

    return {
        "text_result": text_result,
        "header": header,
        "lines": lines,
        "validation": validation,
    }


def merge_albaran_router_extraction_v1(
    extraction,
    routed,
):
    if not routed:
        return extraction

    out = (
        dict(extraction)
        if isinstance(
            extraction,
            dict,
        )
        else {}
    )

    detected = out.get("detected")

    if not isinstance(detected, dict):
        detected = {}

    header = (
        routed.get("header")
        or {}
    )

    fields = (
        "numero_documento",
        "num_albaran_proveedor",
        "fecha",
        "fecha_iso",
        "base_imponible",
        "iva",
        "total",
        "importe_albaran",
        "iva_porcentaje",
        "bruto",
        "descuento",
    )

    for field in fields:

        value = header.get(field)

        if value not in (
            None,
            "",
        ):
            detected[field] = value

    lines = (
        routed.get("lines")
        or {}
    )

    lineas = lines.get(
        "lineas"
    ) or []

    detected[
        "lineas_detectadas"
    ] = len(lineas)

    out["detected"] = detected

    out[
        "albaran_template_router_canonical_v1"
    ] = routed.get(
        "validation"
    ) or {}

    out["template_header"] = header

    out["template_lines"] = {
        "parser": lines.get("parser"),
        "lineas_detectadas": len(
            lineas
        ),
        "total_lineas": lines.get(
            "total_lineas"
        ),
    }

    out["parser_key"] = (
        routed.get(
            "validation",
            {},
        ).get("parser_key")
        or ""
    )

    validation = (
        routed.get("validation")
        or {}
    )

    if (
        validation.get("number_ok")
        and validation.get("date_ok")
        and validation.get(
            "header_math_ok"
        )
        and validation.get(
            "lines_match_base"
        )
    ):
        out["confidence"] = 100
        out["confidence_label"] = "ALTA"

    return out


def extract_albaran_lines_routed_v1(
    text,
    *,
    parser_key,
    pdf_path=None,
    plantilla=None,
    max_pages=10,
):
    """
    Solo actúa sobre parser_key registrados.

    Para el resto devuelve None.
    """

    spec = get_registered_albaran_parser_v1(
        parser_key
    )

    if not spec:
        return None

    source_text = str(
        text
        or ""
    )

    if (
        not source_text.strip()
        and pdf_path
    ):
        text_result = (
            extract_document_text_v1(
                pdf_path,
                max_pages=max_pages,
            )
        )

        source_text = (
            text_result.get("text")
            or ""
        )

    config = _parser_config_v1(
        spec,
        plantilla=plantilla,
    )

    return spec["lines"](
        source_text,
        config=config,
    )
