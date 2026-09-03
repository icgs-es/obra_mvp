"""
PORTAL INTASA · FACTURA TEMPLATE ROUTER CANONICAL V1

Arquitectura:
    PDF
      -> texto canónico
      -> parser seleccionado por plantilla/parser_key
      -> cabecera + líneas
      -> validación matemática
      -> payload

Los parsers registrados aquí NO redefinen los entrypoints globales
de facturas_pdf.py.

Los parser_key no migrados siguen utilizando el sistema legacy.
"""

# FACTURA_TEMPLATE_ROUTER_CANONICAL_V1

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import re
import shutil
import subprocess


MONEY_2_RE = (
    r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}"
)

MONEY_4_RE = (
    r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{4}"
)


def decimal_es_v1(value, default=None):
    raw = str(
        value
        if value is not None
        else ""
    ).strip()

    raw = (
        raw
        .replace("€", "")
        .replace("\xa0", "")
        .replace(" ", "")
        .replace("%", "")
    )

    if not raw:
        return default

    if "," in raw:
        raw = (
            raw
            .replace(".", "")
            .replace(",", ".")
        )

    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return default


def fmt_v1(value, places="0.00"):
    value = (
        value
        if isinstance(value, Decimal)
        else decimal_es_v1(
            value,
            Decimal("0"),
        )
    )

    return str(
        value.quantize(
            Decimal(places),
            rounding=ROUND_HALF_UP,
        )
    )


def extract_pdf_text_canonical_v1(
    path,
    *,
    max_pages=3,
):
    """
    Para PDF digital prioriza pdftotext -layout.

    Motivo:
    conserva columnas y filas mucho mejor que pypdf
    en facturas con tablas.

    Si no está disponible o falla, delega al extractor
    existente de PORTAL INTASA.
    """

    pdf_path = Path(path)

    exe = shutil.which("pdftotext")

    if exe:
        try:
            proc = subprocess.run(
                [
                    exe,
                    "-layout",
                    "-f",
                    "1",
                    "-l",
                    str(max(1, int(max_pages or 3))),
                    str(pdf_path),
                    "-",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )

            text = proc.stdout or ""

            if (
                proc.returncode == 0
                and len(text.strip()) >= 80
            ):
                return {
                    "text": text,
                    "method": "pdftotext_layout",
                    "ocr_used": False,
                    "returncode": proc.returncode,
                }

        except Exception:
            pass

    from apps.gestion.services.pdf_extractor import (
        extract_pdf_text,
    )

    result = extract_pdf_text(
        str(pdf_path),
        max_pages=max_pages,
    )

    return {
        "text": result.get("text") or "",
        "method": (
            result.get("method")
            or "legacy_extract_pdf_text"
        ),
        "ocr_used": bool(
            result.get("ocr_used")
        ),
        "legacy": result,
    }


# =====================================================================
# LUQUE · parser migrado al registro
# =====================================================================

def _luque_header_v1(text):
    """
    Parser de formato LUQUE.

    No contiene números de una factura concreta.
    La plantilla seleccionada gobierna el parser.
    """

    raw = str(text or "")

    result = {
        "numero_documento": "",
        "num_factura_proveedor": "",
        "fecha": "",
        "fecha_iso": "",
        "base_imponible": "",
        "iva": "",
        "total": "",
        "forma_pago": "",
        "vencimiento": "",
    }

    # Ejemplo estructural:
    # L   6698   31- 07- 2026
    invoice = re.search(
        r"(?m)^\s*"
        r"(?P<serie>[A-Z])\s+"
        r"(?P<numero>\d+)\s+"
        r"(?P<dia>\d{2})-\s*"
        r"(?P<mes>\d{2})-\s*"
        r"(?P<year>\d{4})\b",
        raw,
    )

    if invoice:
        serie = invoice.group("serie")
        numero = invoice.group("numero")
        dia = invoice.group("dia")
        mes = invoice.group("mes")
        year = invoice.group("year")

        documento = f"{serie}-{numero}"

        result[
            "numero_documento"
        ] = documento

        result[
            "num_factura_proveedor"
        ] = documento

        result["fecha"] = (
            f"{dia}/{mes}/{year}"
        )

        result["fecha_iso"] = (
            f"{year}-{mes}-{dia}"
        )

    # Pie fiscal:
    # buscar etiquetas primero, nunca números aleatorios
    # del cuerpo de factura.
    lines = raw.splitlines()

    footer_idx = None

    for idx, line in enumerate(lines):
        upper = line.upper()

        if (
            "BASE IVA" in upper
            and "% IVA" in upper
            and "CUOTA IVA" in upper
        ):
            footer_idx = idx
            break

    if footer_idx is not None:

        for line in lines[
            footer_idx + 1:
            footer_idx + 7
        ]:

            values_raw = re.findall(
                MONEY_2_RE,
                line,
            )

            values = [
                decimal_es_v1(v)
                for v in values_raw
            ]

            for idx, value in enumerate(values):

                if (
                    value
                    in {
                        Decimal("21.00"),
                        Decimal("10.00"),
                        Decimal("4.00"),
                    }
                    and idx >= 1
                    and idx + 1 < len(values)
                ):
                    base = values[idx - 1]
                    iva = values[idx + 1]

                    result[
                        "base_imponible"
                    ] = fmt_v1(base)

                    result[
                        "iva"
                    ] = fmt_v1(iva)

                    break

            if (
                result["base_imponible"]
                and result["iva"]
            ):
                break

    # Total por etiqueta.
    total_match = re.search(
        r"IMPORTE\s+TOTAL\s*("
        + MONEY_2_RE
        + r")",
        raw,
        re.IGNORECASE,
    )

    if not total_match:
        total_match = re.search(
            r"("
            + MONEY_2_RE
            + r")"
            r"\s+IMPORTE\s+TOTAL\b",
            raw,
            re.IGNORECASE,
        )

    if total_match:
        result["total"] = fmt_v1(
            total_match.group(1)
        )

    # Vencimiento: fecha seguida del importe.
    venc = re.search(
        r"\b"
        r"(?P<dia>\d{2})-"
        r"(?P<mes>\d{2})-"
        r"(?P<year>\d{4})"
        r"\s+"
        r"(?:"
        + MONEY_2_RE
        + r")"
        r"\s*€",
        raw,
    )

    if venc:
        result["vencimiento"] = (
            f"{venc.group('year')}-"
            f"{venc.group('mes')}-"
            f"{venc.group('dia')}"
        )

    upper = raw.upper()

    if (
        "TRANSFERENCIA 30 DÍAS" in upper
        or "TRANSFERENCIA 30 DIAS" in upper
    ):
        result["forma_pago"] = (
            "Transferencia 30 días"
        )

    return result


_LUQUE_SUFFIX_RE = re.compile(
    r"(?P<qty>"
    + MONEY_2_RE
    + r")"
    r"\s+"
    r"(?P<price>"
    + MONEY_4_RE
    + r")"
    r"(?:\s+(?P<dto1>"
    + MONEY_2_RE
    + r"))?"
    r"(?:\s+(?P<dto2>"
    + MONEY_2_RE
    + r"))?"
    r"\s+"
    r"(?P<amount>"
    + MONEY_2_RE
    + r")"
    r"\s*$"
)


def _luque_lines_v1(text):
    raw = str(text or "")

    lineas = []
    warnings = []

    current_albaran = ""
    current_fecha_albaran = ""
    current_item = None

    serial_note_count = 0

    total_lineas = Decimal("0.00")

    albaran_re = re.compile(
        r"Albar[aá]n\s+n[ºo]?\s*/\s*"
        r"(?P<num>[\d.]+)"
        r"\s+de\s+fecha\s+"
        r"(?P<fecha>\d{2}/\d{2}/\d{4})",
        re.IGNORECASE,
    )

    code_re = re.compile(
        r"^\s*(?P<codigo>\d{6})\s+"
        r"(?P<body>.+?)\s*$"
    )

    footer_tokens = (
        "IMPORTE NETO",
        "BASE IVA",
        "CUOTA IVA",
        "FORMAS DE PAGO",
        "VENCIMIENTOS",
        "IMPORTE TOTAL",
        "LA POSESIÓN",
        "LA POSESION",
    )

    for raw_line in raw.splitlines():

        line = raw_line.rstrip()

        if not line.strip():
            continue

        upper = line.upper()

        if any(
            token in upper
            for token in footer_tokens
        ):
            if (
                "IMPORTE NETO" in upper
                or "FORMAS DE PAGO" in upper
                or "VENCIMIENTOS" in upper
            ):
                current_item = None
            continue

        ma = albaran_re.search(line)

        if ma:
            current_albaran = (
                ma.group("num").strip()
            )

            current_fecha_albaran = (
                ma.group("fecha").strip()
            )

            current_item = None
            continue

        mc = code_re.match(line)

        if mc:
            codigo = mc.group("codigo")
            body = mc.group("body")

            # NºSERIE es metadato del artículo anterior.
            if (
                "NºSERIE" in body.upper()
                or "N°SERIE" in body.upper()
                or "NO SERIE" in body.upper()
            ):
                serial_note_count += 1

                if lineas:
                    raw_data = lineas[-1].setdefault(
                        "raw_data",
                        {},
                    )

                    seriales = raw_data.setdefault(
                        "seriales",
                        [],
                    )

                    seriales.append(
                        body.strip()
                    )

                current_item = None
                continue

            suffix = _LUQUE_SUFFIX_RE.search(
                body
            )

            if not suffix:
                warnings.append(
                    "Línea con código sin columnas "
                    f"económicas interpretables: "
                    f"{codigo}"
                )

                current_item = None
                continue

            cantidad = decimal_es_v1(
                suffix.group("qty")
            )

            precio = decimal_es_v1(
                suffix.group("price")
            )

            dto1 = decimal_es_v1(
                suffix.group("dto1"),
                Decimal("0"),
            )

            dto2 = decimal_es_v1(
                suffix.group("dto2"),
                Decimal("0"),
            )

            importe = decimal_es_v1(
                suffix.group("amount")
            )

            bruto = (
                cantidad * precio
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            esperado = (
                bruto
                * (
                    Decimal("100") - dto1
                )
                / Decimal("100")
                * (
                    Decimal("100") - dto2
                )
                / Decimal("100")
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            error = abs(
                esperado - importe
            )

            if error > Decimal("0.02"):
                warnings.append(
                    f"Línea {codigo}: "
                    f"validación matemática no cuadra "
                    f"({esperado} != {importe})."
                )

            descripcion = (
                body[:suffix.start()]
                .strip()
            )

            importe_descuento = (
                bruto - importe
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            if bruto:
                descuento_efectivo = (
                    importe_descuento
                    / bruto
                    * Decimal("100")
                ).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
            else:
                descuento_efectivo = (
                    Decimal("0.00")
                )

            iva_linea = (
                importe
                * Decimal("21")
                / Decimal("100")
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )

            item = {
                "linea": len(lineas) + 1,
                "codigo": codigo,
                "codigo_detectado": codigo,
                "descripcion": descripcion,
                "descripcion_detectada": (
                    descripcion
                ),
                "unidad": "UN",
                "cantidad": fmt_v1(
                    cantidad,
                    "0.0000",
                ),
                "precio": fmt_v1(
                    precio,
                    "0.0000",
                ),
                "precio_unitario": fmt_v1(
                    precio,
                    "0.0000",
                ),
                "descuento": fmt_v1(
                    descuento_efectivo
                ),
                "descuento_porcentaje": fmt_v1(
                    descuento_efectivo
                ),
                "descuento_1": fmt_v1(
                    dto1
                ),
                "descuento_2": fmt_v1(
                    dto2
                ),
                "importe_descuento": fmt_v1(
                    importe_descuento
                ),
                "importe": fmt_v1(
                    importe
                ),
                "importe_linea": fmt_v1(
                    importe
                ),
                "importe_calculado": fmt_v1(
                    importe
                ),
                "iva_porcentaje": "21.00",
                "importe_iva_linea": fmt_v1(
                    iva_linea
                ),
                "total_linea_con_iva": fmt_v1(
                    importe + iva_linea
                ),
                "num_albaran_proveedor": (
                    current_albaran
                ),
                "albaran_numero": (
                    current_albaran
                ),
                "fecha_albaran": (
                    current_fecha_albaran
                ),
                "raw_line": line.strip(),
                "raw_data": {
                    "source": (
                        "factura_template_router_v1"
                    ),
                    "parser_key": (
                        "luque_factura_valorada_v1"
                    ),
                    "validation_error": (
                        fmt_v1(error)
                    ),
                    "bruto_linea": (
                        fmt_v1(bruto)
                    ),
                    "descuento_1": (
                        fmt_v1(dto1)
                    ),
                    "descuento_2": (
                        fmt_v1(dto2)
                    ),
                },
            }

            lineas.append(item)
            current_item = item

            total_lineas += importe

            continue

        # Continuación textual de la descripción.
        if current_item:

            stripped = line.strip()

            if (
                stripped
                and not stripped.upper().startswith(
                    (
                        "REFERENCIA",
                        "DESCRIPCIÓN",
                        "DESCRIPCION",
                        "FACTURA",
                        "SERIE",
                    )
                )
            ):
                current_item["descripcion"] = (
                    current_item["descripcion"]
                    + " "
                    + stripped
                ).strip()

                current_item[
                    "descripcion_detectada"
                ] = current_item[
                    "descripcion"
                ]

    return {
        "parser": "luque_factura_valorada_v1",
        "parser_key": (
            "luque_factura_valorada_v1"
        ),
        "lineas": lineas,
        "total_lineas": fmt_v1(
            total_lineas
        ),
        "warnings": warnings,
        "serial_note_count": (
            serial_note_count
        ),
        "text_source": (
            "pdftotext_layout_or_fallback"
        ),
    }


# =====================================================================
# DIFALAC · factura valorada
# =====================================================================

_DIFALAC_MONEY_RE_V1 = re.compile(r"-?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}")
_DIFALAC_WORK_REFERENCE_RE_V1 = re.compile(
    r"^\s*(?:\d+(?:[,.]\d+)?\s+)?(?:VIV(?:IENDA)?|CASA)\s*-?\s*\d+[A-Z0-9/-]*\s*$",
    re.IGNORECASE,
)


def _difalac_footer_amounts_v1(text):
    """Extract footer amounts by their column labels, never by fixed values."""
    raw = str(text or "")
    header = re.search(
        r"(?P<labels>(?:\d+(?:[,.]\d+)?\s*%\s*Descuento\s+)?"
        r"(?:\d+(?:[,.]\d+)?\s*%\s*de\s*Retenci[oó]n\s+)?"
        r"Suma\s+Total\s+Base\s+Imponible\s+"
        r"(?:\d+(?:[,.]\d+)?\s*%\s*de\s*I\.?V\.?A\.?\s+)?"
        r"Total\s+factura)(?P<values>.{0,600})",
        raw, re.IGNORECASE | re.DOTALL,
    )
    if not header:
        return {}
    labels = re.findall(
        r"\d+(?:[,.]\d+)?\s*%\s*Descuento|\d+(?:[,.]\d+)?\s*%\s*de\s*Retenci[oó]n|"
        r"Suma\s+Total|Base\s+Imponible|\d+(?:[,.]\d+)?\s*%\s*de\s*I\.?V\.?A\.?|Total\s+factura",
        header.group("labels"), re.IGNORECASE,
    )
    amounts = _DIFALAC_MONEY_RE_V1.findall(header.group("values"))
    if len(amounts) < len(labels):
        return {}
    result = {}
    for label, amount in zip(labels, amounts):
        normalized = re.sub(r"\s+", " ", label).upper()
        if normalized == "BASE IMPONIBLE":
            result["base_imponible"] = decimal_es_v1(amount)
        elif normalized == "SUMA TOTAL":
            result["suma_total"] = decimal_es_v1(amount)
        elif "I.V.A" in normalized or "IVA" in normalized:
            result["iva"] = decimal_es_v1(amount)
        elif normalized == "TOTAL FACTURA":
            result["total"] = decimal_es_v1(amount)
    return result


def _difalac_header_v1(text):
    """Header parser for the DISEÑO FABRICACION Y LACADO invoice layout."""
    raw = str(text or "")
    footer = _difalac_footer_amounts_v1(raw)
    result = {"numero_documento": "", "num_factura_proveedor": "", "fecha": "", "fecha_iso": "", "base_imponible": "", "iva": "", "total": ""}
    invoice = re.search(r"(?im)^\s*N[úu]mero\s*:\s*(?P<number>[^\r\n]+)", raw)
    if invoice:
        number = invoice.group("number").strip()
        result["numero_documento"] = number
        result["num_factura_proveedor"] = number
    date_match = re.search(r"(?im)^\s*FECHA\s*:\s*(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4})\b", raw)
    if date_match:
        result["fecha"] = date_match.group(0).split(":", 1)[1].strip()
        result["fecha_iso"] = "{year}-{month}-{day}".format(**date_match.groupdict())
    for source, target in (("base_imponible", "base_imponible"), ("iva", "iva"), ("total", "total")):
        if footer.get(source) is not None:
            result[target] = fmt_v1(footer[source])
    return result


def _difalac_is_noise_v1(line):
    normalized = re.sub(r"\s+", " ", str(line or "").strip()).upper()
    if not normalized or _DIFALAC_WORK_REFERENCE_RE_V1.match(normalized):
        return True
    return normalized.startswith((
        "ARTICULO ", "UDS ", "DESCRIPCION", "DESCRIPCIÓN", "DTO ", "IMPORTE", "TOTAL",
        "DATOS DE LA FACTURA", "DATOS DEL CLIENTE", "NUMERO:", "NÚMERO:", "FECHA:",
        "FORMA DE PAGO", "OBRA:", "OBSERVACIONES:", "PÁGINA ", "PAGINA ",
        "DISEÑO FABRICACION", "C.I.F.", "CIF:", "TLF:", "EMAIL:", "INSCRITA EN ",
        "SUMA TOTAL", "BASE IMPONIBLE", "A PERCIBIR",
    ))


def _difalac_lines_v1(text):
    """Parse valued DIFALAC rows, including wrapped descriptions and page breaks."""
    raw = str(text or "")
    footer = _difalac_footer_amounts_v1(raw)
    result = {
        "parser": "difalac_factura_valorada_v1", "parser_key": "difalac_factura_valorada_v1",
        "lineas": [], "total_lineas": "0.00", "warnings": [], "validation_tolerance": "0.05",
        "line_sum_matches_base": False, "expected_base": "", "text_source": "pdftotext_layout_or_fallback",
    }
    table_header = re.search(r"ARTICULO\s+UDS\s+DESCRIPCI[OÓ]N\s+Dto\s+IMPORTE\s+TOTAL", raw, re.IGNORECASE)
    body = raw[table_header.end():] if table_header else raw
    footer_start = re.search(r"(?im)^\s*(?:\d+(?:[,.]\d+)?\s*%\s+Descuento|Suma\s+Total\s+Base\s+Imponible)", body)
    if footer_start:
        body = body[:footer_start.start()]
    total_lineas = Decimal("0.00")
    current = None
    line_pattern = re.compile(
        r"^\s*(?:(?P<codigo>(?:[A-Z][A-Z0-9./_-]*|\d{3,}))\s+)?"
        r"(?P<cantidad>\d+(?:[,.]\d+)?)\s+(?P<descripcion>.+?)\s*$", re.IGNORECASE,
    )
    for source_line in body.splitlines():
        line = re.sub(r"\s+", " ", source_line.strip())
        if not line:
            continue
        if _difalac_is_noise_v1(line):
            current = None if _DIFALAC_WORK_REFERENCE_RE_V1.match(line) else current
            continue
        monies = list(_DIFALAC_MONEY_RE_V1.finditer(line))
        if len(monies) >= 2:
            price_match, amount_match = monies[-2], monies[-1]
            parsed = line_pattern.match(line[:price_match.start()].strip())
            if parsed and re.search(r"[A-ZÁÉÍÓÚÜÑ]", parsed.group("descripcion"), re.IGNORECASE):
                cantidad = decimal_es_v1(parsed.group("cantidad"))
                precio = decimal_es_v1(price_match.group(0))
                importe = decimal_es_v1(amount_match.group(0))
                if cantidad is not None and cantidad != 0 and precio is not None and importe is not None:
                    expected = (cantidad * precio).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    validation_error = abs(expected - importe)
                    descripcion = parsed.group("descripcion").strip()
                    item = {
                        "linea": len(result["lineas"]) + 1, "codigo": parsed.group("codigo") or "",
                        "codigo_detectado": parsed.group("codigo") or "", "codigo_proveedor": parsed.group("codigo") or "",
                        "descripcion": descripcion, "descripcion_detectada": descripcion,
                        "cantidad": fmt_v1(cantidad, "0.0000"), "precio": fmt_v1(precio, "0.0000"),
                        "precio_unitario": fmt_v1(precio, "0.0000"), "importe": fmt_v1(importe),
                        "importe_linea": fmt_v1(importe), "raw_line": line,
                        "raw_data": {"source": "factura_template_router_v1", "parser_key": "difalac_factura_valorada_v1", "validation_error": fmt_v1(validation_error)},
                    }
                    if validation_error > Decimal("0.05"):
                        result["warnings"].append("DIFALAC: cantidad × precio no coincide con importe en línea %s." % item["linea"])
                    result["lineas"].append(item)
                    total_lineas += importe
                    current = item
                    continue
        if current and not _DIFALAC_MONEY_RE_V1.search(line) and re.search(r"[A-ZÁÉÍÓÚÜÑ]", line, re.IGNORECASE):
            current["descripcion"] = (current["descripcion"] + " " + line).strip()
            current["descripcion_detectada"] = current["descripcion"]
            current["raw_line"] = current["raw_line"] + " | " + line
    result["total_lineas"] = fmt_v1(total_lineas)
    expected_base = footer.get("base_imponible")
    if expected_base is not None:
        result["expected_base"] = fmt_v1(expected_base)
        result["line_sum_matches_base"] = abs(total_lineas - expected_base) <= Decimal("0.05")
        if not result["line_sum_matches_base"]:
            result["warnings"].append("DIFALAC: suma de líneas %s no coincide con base %s." % (fmt_v1(total_lineas), fmt_v1(expected_base)))
    else:
        result["warnings"].append("DIFALAC: no se pudo localizar la base imponible del pie.")
    if not result["lineas"]:
        result["warnings"].append("DIFALAC: no se detectaron líneas económicas.")
    return result


# =====================================================================
# REGISTRO
# =====================================================================

FACTURA_TEMPLATE_PARSER_REGISTRY_V1 = {
    "difalac_factura_valorada_v1": {
        "header": _difalac_header_v1,
        "lines": _difalac_lines_v1,
        "prefer_layout": True,
    },
    "luque_factura_valorada_v1": {
        "header": _luque_header_v1,
        "lines": _luque_lines_v1,
        "prefer_layout": True,
    },
}


def get_registered_parser_v1(
    parser_key,
):
    return (
        FACTURA_TEMPLATE_PARSER_REGISTRY_V1
        .get(
            str(
                parser_key
                or ""
            ).strip()
        )
    )


def _sync_header_to_payload_v1(
    payload,
    header,
):
    if not isinstance(payload, dict):
        payload = {}

    if not isinstance(header, dict):
        return payload

    numero = (
        header.get("numero_documento")
        or header.get(
            "num_factura_proveedor"
        )
    )

    fecha = header.get("fecha")
    fecha_iso = header.get("fecha_iso")

    base = header.get("base_imponible")
    iva = header.get("iva")
    total = header.get("total")

    if numero:
        for key in (
            "numero_documento",
            "numero_factura",
            "num_factura_proveedor",
        ):
            payload[key] = numero

    if fecha:
        payload["fecha"] = fecha

    if fecha_iso:
        payload["fecha_iso"] = fecha_iso
        payload["fecha_emision"] = fecha_iso

    if base:
        payload["base_imponible"] = base
        payload[
            "importe_base_imponible"
        ] = base

    if iva:
        payload["iva"] = iva
        payload["importe_iva"] = iva

    if total:
        payload["total"] = total
        payload["importe_factura"] = total

    if header.get("forma_pago"):
        payload["forma_pago"] = (
            header["forma_pago"]
        )

    if header.get("vencimiento"):
        payload["vencimiento"] = (
            header["vencimiento"]
        )

    return payload


def apply_factura_template_router_v1(
    path,
    *,
    parser_key,
    team=None,
    legacy_payload=None,
    max_pages=3,
):
    """
    Cabecera dirigida por la plantilla.

    Si parser_key no está registrado:
        devuelve exactamente el payload legacy.

    Por tanto la migración puede ser progresiva.
    """

    payload = (
        dict(legacy_payload)
        if isinstance(
            legacy_payload,
            dict,
        )
        else {}
    )

    spec = get_registered_parser_v1(
        parser_key
    )

    if not spec:
        return payload

    extracted = (
        extract_pdf_text_canonical_v1(
            path,
            max_pages=max_pages,
        )
    )

    text = extracted.get("text") or ""

    header = spec["header"](text)
    lines = spec["lines"](text)

    payload = _sync_header_to_payload_v1(
        payload,
        header,
    )

    # El texto canónico sustituye únicamente el texto
    # de trabajo; no se persiste en tokens pesados.
    payload["text"] = text

    payload["parser"] = str(parser_key)
    payload["parser_key"] = str(
        parser_key
    )

    base = decimal_es_v1(
        header.get("base_imponible")
    )

    iva = decimal_es_v1(
        header.get("iva")
    )

    total = decimal_es_v1(
        header.get("total")
    )

    line_sum = decimal_es_v1(
        lines.get("total_lineas")
    )

    amount_ok = False
    lines_ok = False

    if (
        base is not None
        and iva is not None
        and total is not None
    ):
        amount_ok = (
            abs(
                (base + iva) - total
            )
            <= Decimal("0.02")
        )

    if (
        base is not None
        and line_sum is not None
    ):
        lines_ok = (
            abs(
                base - line_sum
            )
            <= Decimal("0.02")
        )

    raw_data = payload.get("raw_data")

    if not isinstance(raw_data, dict):
        raw_data = {}

    raw_data[
        "factura_template_router_canonical_v1"
    ] = {
        "parser_key": str(parser_key),
        "text_method": extracted.get(
            "method"
        ),
        "ocr_used": extracted.get(
            "ocr_used",
            False,
        ),
        "amount_equation_ok": amount_ok,
        "line_sum_matches_base": lines_ok,
        "line_count": len(
            lines.get("lineas") or []
        ),
        "line_sum": lines.get(
            "total_lineas"
        ),
        "serial_note_count": lines.get(
            "serial_note_count",
            0,
        ),
    }

    payload["raw_data"] = raw_data

    if (
        amount_ok
        and lines_ok
        and header.get(
            "numero_documento"
        )
        and header.get("fecha_iso")
    ):
        payload["confidence"] = "ALTA"

    return payload


def extract_factura_lines_template_routed_v1(
    text,
    *,
    parser_key,
    factura=None,
    pdf_path=None,
    max_pages=10,
):
    """
    Router de líneas dirigido por plantilla.

    Registrado -> parser aislado.
    No registrado -> router template legacy.
    """

    spec = get_registered_parser_v1(
        parser_key
    )

    if spec:

        source_text = str(text or "")

        if (
            pdf_path
            and spec.get(
                "prefer_layout"
            )
        ):
            extracted = (
                extract_pdf_text_canonical_v1(
                    pdf_path,
                    max_pages=max_pages,
                )
            )

            candidate = (
                extracted.get("text")
                or ""
            )

            if candidate.strip():
                source_text = candidate

        return spec["lines"](
            source_text
        )

    # Compatibilidad completa con los parsers
    # ya migrados parcialmente al router V1.
    from apps.gestion.services import (
        facturas_pdf,
    )

    legacy_router = getattr(
        facturas_pdf,
        "extract_factura_lines_by_template_v1",
        None,
    )

    if callable(legacy_router):
        return legacy_router(
            text,
            parser_key=parser_key,
            factura=factura,
        )

    return None
