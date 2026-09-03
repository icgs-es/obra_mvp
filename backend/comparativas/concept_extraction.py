"""
Extracción genérica de conceptos de presupuestos.

Principios:
- no contiene reglas por proveedor;
- no llama a OpenAI;
- no escribe en base de datos;
- conserva evidencia y números de línea;
- solo acepta relaciones económicas demostrables;
- utiliza layout PDF como fallback estructural;
- nunca asigna números huérfanos por mera posición.
"""

import re
import subprocess
import unicodedata

from decimal import Decimal, InvalidOperation


MONEY_PATTERN = (
    r"(?:"
    r"\d{1,3}(?:\.\d{3})*"
    r"|\d+"
    r"),\d{2}"
)

MONEY_RE = re.compile(
    MONEY_PATTERN
)

MONEY_FULL_RE = re.compile(
    rf"^{MONEY_PATTERN}$"
)

# Formatos documentales frecuentes fuera de tablas:
# 1800/Euros, 1247,4/EUROS, 5.940 EUR, etc.
# Solo se utiliza cuando existe una unidad monetaria
# explícita; nunca convierte números huérfanos en dinero.
LOOSE_EURO_RE = re.compile(
    r"(?P<number>"
    r"\d+(?:\.\d{3})*"
    r"(?:[,.]\d{1,2})?"
    r")"
    r"\s*(?:/\s*)?"
    r"(?:EUROS?|EUR|€)",
    re.I,
)

PAGE_RE = re.compile(
    r"---\s*PAGE\s+(\d+)",
    re.I,
)

UNIT_PATTERN = (
    r"(?:"
    r"UD|U|ML|M\.L\.|M2|M²|M3|M³|"
    r"KG|GR|L|LT|H|HR|PA|P\.A\.|"
    r"UN|UND"
    r")"
)

STRUCTURED_RE = re.compile(
    rf"^\s*"
    rf"(?P<price>{MONEY_PATTERN})"
    rf"\s+"
    rf"(?P<packed>[\d.,]+)"
    rf"\s*"
    rf"(?P<unit>{UNIT_PATTERN})"
    rf"\s+"
    rf"(?P<title>.+?)"
    rf"(?:\s+"
    rf"(?P<trailing>{MONEY_PATTERN})"
    rf")?"
    rf"\s*$",
    re.I,
)

ZERO_SECTION_RE = re.compile(
    rf"^\s*0,000"
    rf"(?P<title>.+?)"
    rf"\s+0,00\s*$",
    re.I,
)

EXCLUSION_TOKENS = (
    "NO INCLUYE",
    "NO SE INCLUYE",
    "NO ENTRA",
    "NO ESTAN INCLUID",
    "NO ESTÁN INCLUID",
    "EXCLUIDO",
    "EXCLUIDA",
    "SE EXCLUYE",
)

ACTION_STARTS = (
    "REALIZAR TRABAJOS",
    "INSTALACION ",
    "INSTALACIÓN ",
    "SUMINISTRO ",
    "COLOCACION ",
    "COLOCACIÓN ",
    "MONTAJE ",
    "EJECUCION ",
    "EJECUCIÓN ",
)

STOP_TOKENS = (
    "BASE IMPONIBLE",
    "SUBTOTAL",
    "TOTAL:",
    "TOTAL IMPORTE",
    "CUOTA IVA",
    "RESUMEN DE IMPORTES",
    "% IVA",
    "IVA:",
    "FORMA DE PAGO",
)


EXCLUSION_CONTINUATION_BOUNDARIES = (
    "SE ABONARA",
    "SE ABONARAN",
    "RESTO,",
    "RESTO ",
    "FORMA DE PAGO",
    "CONDICIONES DE PAGO",
    "PAGO:",
    "CONFORME",
    "NOMBRE Y APELLIDOS",
    "FIRMA DEL CLIENTE",
    "FIRMA Y SELLO",
    "DNI:",
)


def _norm(value):
    value = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )

    value = "".join(
        char
        for char in value
        if not unicodedata.combining(
            char
        )
    )

    return re.sub(
        r"\s+",
        " ",
        value.upper(),
    ).strip()


def _money(value):
    value = (
        str(value or "")
        .replace("€", "")
        .replace(" ", "")
        .strip()
    )

    if not value:
        return None

    if "," in value:
        value = (
            value
            .replace(".", "")
            .replace(",", ".")
        )

    try:
        return Decimal(value)
    except (
        InvalidOperation,
        ValueError,
    ):
        return None


def _decimal_str(value):
    if value is None:
        return ""

    return format(value, "f")


def _letters(value):
    return sum(
        1
        for char in str(value or "")
        if char.isalpha()
    )


def _is_page_marker(line):
    return bool(
        PAGE_RE.search(
            line or ""
        )
    )


def _is_stop(line):
    normalized = _norm(line)

    return any(
        token in normalized
        for token in STOP_TOKENS
    )


def _is_exclusion(line):
    normalized = _norm(line)

    return any(
        token in normalized
        for token in EXCLUSION_TOKENS
    )


def _is_exclusion_continuation_boundary(
    line,
):
    normalized = _norm(line)

    return normalized.startswith(
        EXCLUSION_CONTINUATION_BOUNDARIES
    )


def _is_contact(line):
    normalized = _norm(line)

    if "@" in str(line or ""):
        return True

    prefixes = (
        "FECHA:",
        "NIF:",
        "CIF:",
        "TEL:",
        "TELF:",
        "TELFS:",
        "FAX:",
        "E-MAIL:",
        "EMAIL:",
        "INTERNET:",
        "WWW.",
        "PAGINA ",
        "PAGE ",
        "FIRMA ",
        "CONFORME ",
    )

    return normalized.startswith(
        prefixes
    )


def _loose_euro_amount(line):
    matches = list(
        LOOSE_EURO_RE.finditer(
            str(line or "")
        )
    )

    if not matches:
        return None

    raw = (
        matches[-1]
        .group("number")
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _strip_loose_euro_amount(line):
    value = str(line or "")
    matches = list(
        LOOSE_EURO_RE.finditer(
            value
        )
    )

    if not matches:
        return value.strip()

    match = matches[-1]

    cleaned = (
        value[:match.start()]
        + value[match.end():]
    )

    return cleaned.strip(
        " \t.-:…"
    )


def _is_description_heading(line):
    normalized = (
        _norm(line)
        .strip()
        .rstrip(":")
        .strip()
    )

    return normalized == "DESCRIPCION"


def _is_payment_boundary(line):
    normalized = _norm(line)

    return normalized.startswith(
        (
            "FORMA DE PAGO",
            "CONDICIONES DE PAGO",
            "SE ABONARA",
            "SE ABONARAN",
            "PAGO:",
        )
    )


def _is_economic_summary_line(line):
    normalized = _norm(line)

    if normalized.startswith(
        (
            "TOTAL",
            "BASE IMPONIBLE",
            "BASE IVA",
            "BASE I.V.A",
            "SUBTOTAL",
            "CUOTA IVA",
            "% IVA",
            "IVA:",
        )
    ):
        return True

    if re.match(
        r"^\d+(?:[.,]\d+)?%\s*IVA\b",
        normalized,
    ):
        return True

    # Pie económico degradado por OCR aunque
    # exista texto anterior en la misma línea:
    #
    # ... BASE LVA. 7.552,00
    #     CUOTA VAG 585,92
    #     TOTAL PREV... 37,92
    #
    # Aquí no corregimos cifras. Únicamente
    # evitamos que se convierta en concepto.
    padded = (
        " "
        + normalized
        + " "
    )

    has_base = (
        " BASE "
        in padded
        or " BASE LVA "
        in padded
        or " BASE I V A "
        in padded
        or " BASE IVA "
        in padded
    )

    has_tax = (
        " IVA "
        in padded
        or " I V A "
        in padded
        or " CUOTA "
        in padded
        or " VAG "
        in padded
        or " LVA "
        in padded
    )

    has_total = (
        " TOTAL "
        in padded
        or " TOTAL PRESUPUESTO "
        in padded
        or " TOTAL PREV "
        in padded
    )

    money_count = len(
        re.findall(
            r"\d+"
            r"(?:[.,]\d{3})*"
            r"[.,]\d{2}",
            str(line or ""),
        )
    )

    if (
        has_base
        and has_tax
        and has_total
        and money_count >= 2
    ):
        return True

    return False




def _economic_summary_signals(value):
    normalized = _norm(
        value
    )

    padded = (
        " "
        + normalized
        + " "
    )

    has_base = (
        " BASE "
        in padded
        or " BASE IMPONIBLE "
        in padded
        or " BASE IVA "
        in padded
        or " BASE I V A "
        in padded
        or " BASE LVA "
        in padded
        or normalized.startswith(
            "SUBTOTAL"
        )
    )

    has_tax = (
        " IVA "
        in padded
        or " I V A "
        in padded
        or " CUOTA "
        in padded
        or " VAG "
        in padded
        or " LVA "
        in padded
    )

    has_total = (
        " TOTAL "
        in padded
        or " TOTAL PRESUPUESTO "
        in padded
        or " TOTAL PREV "
        in padded
        or " IMPORTE TOTAL "
        in padded
    )

    money_count = len(
        re.findall(
            r"\d+"
            r"(?:[.,]\d{3})*"
            r"[.,]\d{2}",
            str(value or ""),
        )
    )

    return {
        "has_base": has_base,
        "has_tax": has_tax,
        "has_total": has_total,
        "money_count": money_count,
    }


def _is_economic_summary_continuation(
    line,
):
    """
    Solo permite extender un pie económico sobre
    líneas inmediatamente posteriores que siguen
    pareciendo cabecera/valores económicos.

    Una descripción normal de partida corta la
    búsqueda para no absorber conceptos reales.
    """
    line = str(
        line or ""
    ).strip()

    if not line:
        return True

    if _is_page_marker(
        line
    ):
        return False

    signals = (
        _economic_summary_signals(
            line
        )
    )

    if (
        signals["has_base"]
        or signals["has_tax"]
        or signals["has_total"]
    ):
        return True

    # Fila puramente numérica debajo de una
    # cabecera BASE / IVA / TOTAL.
    if (
        signals["money_count"] >= 1
        and _letters(line) <= 10
    ):
        return True

    return False


def _economic_summary_line_numbers(
    lines,
):
    """
    Devuelve las líneas pertenecientes a un
    resumen económico compacto o partido.

    Regla fail-closed:
      1. El inicio debe contener BASE + señal fiscal.
      2. Solo mira como máximo dos líneas posteriores.
      3. No atraviesa una línea que parezca concepto.
      4. El conjunto debe terminar conteniendo TOTAL.
      5. Debe haber al menos dos importes monetarios.

    No interpreta ni corrige importes.
    Únicamente evita convertir la cabecera/pie
    financiero en conceptos de alcance.
    """
    result = set()

    numbers = sorted(
        lines
    )

    for number in numbers:
        line = (
            lines.get(
                number,
                ""
            )
            or ""
        ).strip()

        if not line:
            continue

        start_signals = (
            _economic_summary_signals(
                line
            )
        )

        if not (
            start_signals[
                "has_base"
            ]
            and start_signals[
                "has_tax"
            ]
        ):
            continue

        combined_parts = [
            line
        ]

        block_numbers = [
            number
        ]

        combined_signals = (
            _economic_summary_signals(
                line
            )
        )

        if (
            combined_signals[
                "has_total"
            ]
            and combined_signals[
                "money_count"
            ] >= 2
        ):
            result.add(
                number
            )
            continue

        non_empty_lookahead = 0

        for candidate_number in range(
            number + 1,
            number + 4,
        ):
            candidate = (
                lines.get(
                    candidate_number,
                    ""
                )
                or ""
            ).strip()

            if not candidate:
                continue

            non_empty_lookahead += 1

            if non_empty_lookahead > 2:
                break

            if not (
                _is_economic_summary_continuation(
                    candidate
                )
            ):
                break

            combined_parts.append(
                candidate
            )

            block_numbers.append(
                candidate_number
            )

            combined = " ".join(
                combined_parts
            )

            combined_signals = (
                _economic_summary_signals(
                    combined
                )
            )

            if (
                combined_signals[
                    "has_base"
                ]
                and combined_signals[
                    "has_tax"
                ]
                and combined_signals[
                    "has_total"
                ]
                and combined_signals[
                    "money_count"
                ] >= 2
            ):
                result.update(
                    block_numbers
                )
                break

    return result


def _is_non_scope_description_line(line):
    normalized = _norm(line)

    return normalized.startswith(
        (
            "NOTA:",
            "OBSERVACIONES:",
            "VALIDEZ:",
            "PLAZO:",
            "GARANTIA:",
            "GARANTÍA:",
        )
    )


def _page_map(lines):
    page = 1
    result = {}

    for number, line in enumerate(
        lines,
        start=1,
    ):
        match = PAGE_RE.search(line)

        if match:
            page = int(
                match.group(1)
            )

        result[number] = page

    return result


def _infer_amount_quantity(
    price,
    packed,
):
    candidates = []

    packed = str(packed or "")

    for position in range(
        1,
        len(packed),
    ):
        amount_raw = packed[:position]
        quantity_raw = packed[position:]

        if not MONEY_FULL_RE.fullmatch(
            amount_raw
        ):
            continue

        if not re.fullmatch(
            r"\d+,\d{3,4}",
            quantity_raw,
        ):
            continue

        amount = _money(
            amount_raw
        )

        quantity = _money(
            quantity_raw
        )

        if (
            amount is None
            or quantity is None
            or quantity <= 0
        ):
            continue

        difference = abs(
            price * quantity
            - amount
        )

        tolerance = max(
            Decimal("0.02"),
            abs(amount)
            * Decimal("0.001"),
        )

        if difference <= tolerance:
            candidates.append(
                (
                    difference,
                    amount,
                    quantity,
                )
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item[0]
    )

    _, amount, quantity = (
        candidates[0]
    )

    return {
        "importe": amount,
        "cantidad": quantity,
    }


def _parse_structured_line(line):
    match = STRUCTURED_RE.match(
        line or ""
    )

    if not match:
        return None

    price = _money(
        match.group("price")
    )

    if price is None:
        return None

    inferred = (
        _infer_amount_quantity(
            price,
            match.group("packed"),
        )
    )

    if not inferred:
        return None

    title = (
        match.group("title")
        or ""
    ).strip()

    if _letters(title) < 4:
        return None

    return {
        "titulo": title,
        "cantidad": inferred[
            "cantidad"
        ],
        "unidad": (
            match.group("unit")
            or ""
        ),
        "precio_unitario": price,
        "importe": inferred[
            "importe"
        ],
    }


def extract_pdf_layout_text(
    path,
    *,
    max_pages=10,
):
    command = [
        "pdftotext",
        "-layout",
        "-f",
        "1",
        "-l",
        str(max_pages),
        str(path),
        "-",
    ]

    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )

    return result.stdout


def _layout_columns(line):
    upper = line.upper()

    required = (
        "CONCEPTO",
        "UNIDADES",
    )

    if not all(
        token in upper
        for token in required
    ):
        return None

    concept = upper.find(
        "CONCEPTO"
    )

    units = upper.find(
        "UNIDADES"
    )

    price = upper.find(
        "PRECIO"
    )

    amount = upper.find(
        "IMPORTE"
    )

    iva = upper.find(
        "% IVA"
    )

    if (
        concept < 0
        or units <= concept
    ):
        return None

    return {
        "concept": concept,
        "units": units,
        "price": (
            price
            if price > units
            else None
        ),
        "amount": (
            amount
            if amount > units
            else None
        ),
        "iva": (
            iva
            if iva > units
            else None
        ),
    }


def extract_layout_table(
    layout_text,
):
    lines = (
        layout_text
        or ""
    ).splitlines()

    columns = None
    header_number = None

    for number, line in enumerate(
        lines,
        start=1,
    ):
        columns = _layout_columns(
            line
        )

        if columns:
            header_number = number
            break

    if not columns:
        return []

    candidates = []

    units_start = columns[
        "units"
    ]

    next_column = (
        columns.get("price")
        or columns.get("amount")
        or columns.get("iva")
    )

    if next_column is None:
        next_column = (
            units_start + 20
        )

    for number in range(
        header_number + 1,
        len(lines) + 1,
    ):
        line = lines[
            number - 1
        ]

        if _is_stop(line):
            break

        if not line.strip():
            continue

        title = (
            line[:units_start]
            .strip()
            .strip(".")
            .strip()
        )

        quantity_raw = (
            line[
                units_start:
                next_column
            ]
            .strip()
        )

        if (
            not title
            or _letters(title) < 4
        ):
            continue

        if not re.fullmatch(
            r"\d+(?:[.,]\d{1,4})?",
            quantity_raw,
        ):
            continue

        quantity = _money(
            quantity_raw
        )

        if quantity is None:
            continue

        description = []

        for next_number in range(
            number + 1,
            len(lines) + 1,
        ):
            next_line = lines[
                next_number - 1
            ]

            if (
                not next_line.strip()
            ):
                continue

            if _is_stop(next_line):
                break

            next_title = (
                next_line[
                    :units_start
                ]
                .strip()
                .strip(".")
                .strip()
            )

            next_quantity_raw = (
                next_line[
                    units_start:
                    next_column
                ]
                .strip()
            )

            if (
                next_title
                and _letters(
                    next_title
                ) >= 4
                and re.fullmatch(
                    r"\d+(?:[.,]\d{1,4})?",
                    next_quantity_raw,
                )
            ):
                break

            if next_title:
                description.append(
                    next_title
                )

        candidates.append({
            "strategy": (
                "PDF_LAYOUT_TABLE"
            ),
            "linea_inicio": number,
            "linea_fin": (
                number
                + len(description)
            ),
            "titulo": title,
            "descripcion": " ".join(
                description
            ),
            "cantidad": quantity,
            "unidad": "",
            "precio_unitario": None,
            "importe": None,
            "alcance": "INCLUIDO",
            "confianza": "ALTA",
            "evidencia": line.strip(),
            "contexto": "",
        })

    return candidates


def _previous_money_line(
    money_lines,
    current,
):
    previous = [
        value
        for value in money_lines
        if value < current
    ]

    return max(previous) if previous else 0


def _amount_block_start(
    lines,
    current,
    previous_money,
):
    lower_bound = max(
        previous_money + 1,
        current - 10,
        1,
    )

    numbered = []

    actions = []

    for number in range(
        lower_bound,
        current + 1,
    ):
        line = lines.get(
            number,
            "",
        ).strip()

        normalized = _norm(line)

        if re.match(
            r"^[^A-ZÁÉÍÓÚÑ0-9]*"
            r"\d+\s+[A-ZÁÉÍÓÚÑ]",
            normalized,
        ):
            numbered.append(number)

        if normalized.startswith(
            ACTION_STARTS
        ):
            actions.append(number)

    if numbered:
        return max(numbered)

    if actions:
        return max(actions)

    return current


def _amount_block_end(
    lines,
    current,
    money_lines,
):
    end = current

    maximum = max(
        lines.keys(),
        default=current,
    )

    for number in range(
        current + 1,
        min(
            maximum,
            current + 10,
        ) + 1,
    ):
        line = lines.get(
            number,
            "",
        ).strip()

        if not line:
            continue

        normalized = _norm(line)

        if (
            number in money_lines
            or _is_exclusion(line)
            or _is_stop(line)
            or normalized.startswith(
                ACTION_STARTS
            )
            or re.match(
                r"^[^A-ZÁÉÍÓÚÑ0-9]*"
                r"\d+\s+[A-ZÁÉÍÓÚÑ]",
                normalized,
            )
            or normalized.startswith(
                "VIVIENDA "
            )
        ):
            break

        # Una continuación OCR con mayoría de minúsculas
        # puede formar parte del mismo concepto.
        if (
            line[:1].islower()
            or line.startswith(
                (
                    "|",
                    "EN ",
                    "n ",
                    "A ",
                )
            )
        ):
            end = number
            continue

        break

    return end


def _extract_exclusions(
    lines,
    page_map,
):
    results = []

    maximum = max(
        lines.keys(),
        default=0,
    )

    consumed = set()

    for number in sorted(lines):
        if number in consumed:
            continue

        line = lines[
            number
        ].strip()

        if not _is_exclusion(line):
            continue

        parts = [line]
        end = number

        for next_number in range(
            number + 1,
            min(
                maximum,
                number + 4,
            ) + 1,
        ):
            next_line = lines.get(
                next_number,
                "",
            ).strip()

            if not next_line:
                continue

            if (
                _is_exclusion(next_line)
                or _is_stop(next_line)
                or _is_exclusion_continuation_boundary(
                    next_line
                )
                or MONEY_RE.search(
                    next_line
                )
                or _is_page_marker(
                    next_line
                )
            ):
                break

            parts.append(
                next_line
            )

            consumed.add(
                next_number
            )

            end = next_number

        text = " ".join(parts)

        # Notas contractuales genéricas del tipo:
        # "cualquier trabajo no descrito queda excluido"
        # se conservan fuera de la matriz de conceptos.
        normalized = _norm(text)

        if (
            normalized.startswith(
                "NOTA:"
            )
            and "CUALQUIER TRABAJO" in normalized
        ):
            continue

        results.append({
            "strategy": (
                "EXCLUSION_EXPLICITA"
            ),
            "pagina": page_map.get(
                number,
                1,
            ),
            "linea_inicio": number,
            "linea_fin": end,
            "titulo": text,
            "descripcion": "",
            "cantidad": None,
            "unidad": "",
            "precio_unitario": None,
            "importe": None,
            "alcance": "EXCLUIDO",
            "confianza": "ALTA",
            "evidencia": text,
            "contexto": "",
        })

    return results


def _extract_description_section_concepts(
    lines,
    page_map,
    occupied_ranges,
    exclusion_ranges,
):
    """
    Fallback conservador para presupuestos que expresan
    alcance técnico en una sección DESCRIPCION pero no
    asignan precio individual a cada trabajo.

    No distribuye totales de bloque entre conceptos.
    Cuando existe un TOTAL de bloque explícito, se conserva
    únicamente como contexto documental.
    """
    results = []
    pending_unvalued = []
    active = False

    for number in sorted(lines):
        line = (
            lines.get(
                number,
                "",
            )
            or ""
        ).strip()

        if _is_description_heading(line):
            active = True
            pending_unvalued = []
            continue

        if not active:
            continue

        if not line:
            continue

        if _is_payment_boundary(line):
            break

        if (
            number in occupied_ranges
            or number in exclusion_ranges
            or _is_page_marker(line)
            or _is_contact(line)
            or _is_exclusion(line)
        ):
            continue

        if _is_economic_summary_line(line):
            normalized = _norm(line)

            # Un TOTAL simple situado tras varias líneas
            # descriptivas se conserva como contexto del
            # bloque, pero NO como importe de cada línea.
            if (
                normalized.startswith("TOTAL")
                and not normalized.startswith(
                    "TOTAL DEL"
                )
            ):
                block_total = (
                    _loose_euro_amount(
                        line
                    )
                )

                if (
                    block_total is not None
                    and pending_unvalued
                ):
                    context = (
                        "TOTAL DE BLOQUE "
                        "DOCUMENTAL: "
                        f"{block_total:.2f} EUR"
                    )

                    for result_index in (
                        pending_unvalued
                    ):
                        if not results[
                            result_index
                        ]["contexto"]:
                            results[
                                result_index
                            ][
                                "contexto"
                            ] = context

            pending_unvalued = []
            continue

        if _is_non_scope_description_line(
            line
        ):
            continue

        if _letters(line) < 5:
            continue

        amount = _loose_euro_amount(
            line
        )

        title = (
            _strip_loose_euro_amount(
                line
            )
            if amount is not None
            else line
        )

        if _letters(title) < 5:
            continue

        strategy = (
            "DESCRIPCION_CON_IMPORTE"
            if amount is not None
            else "DESCRIPCION_SIN_IMPORTE"
        )

        results.append({
            "strategy": strategy,
            "pagina": page_map.get(
                number,
                1,
            ),
            "linea_inicio": number,
            "linea_fin": number,
            "titulo": title,
            "descripcion": "",
            "cantidad": None,
            "unidad": "",
            "precio_unitario": None,
            "importe": amount,
            "alcance": "INCLUIDO",
            "confianza": "ALTA",
            "evidencia": line,
            "contexto": "",
        })

        if amount is None:
            pending_unvalued.append(
                len(results) - 1
            )

    return results


def extract_text_concepts(text):
    raw_lines = (
        text
        or ""
    ).splitlines()

    lines = {
        number: line.strip()
        for number, line
        in enumerate(
            raw_lines,
            start=1,
        )
    }

    pages = _page_map(
        raw_lines
    )

    results = []
    consumed = set()

    economic_summary_lines = (
        _economic_summary_line_numbers(
            lines
        )
    )

    consumed.update(
        economic_summary_lines
    )

    current_section = ""

    structured_numbers = []

    for number in sorted(lines):
        line = lines[
            number
        ]

        if number in consumed:
            continue

        # Un resumen BASE / IVA / TOTAL no es
        # una partida aunque el OCR haya pegado
        # texto previo en la misma línea.
        if _is_economic_summary_line(
            line
        ):
            consumed.add(
                number
            )
            continue

        section = ZERO_SECTION_RE.match(
            line
        )

        if section:
            current_section = (
                section.group(
                    "title"
                )
                .strip()
            )

            consumed.add(number)
            continue

        parsed = (
            _parse_structured_line(
                line
            )
        )

        if not parsed:
            continue

        structured_numbers.append(
            number
        )

        # Las descripciones tabulares suelen aparecer
        # justo antes de la fila económica.
        description_parts = []

        previous_structured = max(
            [
                item
                for item
                in structured_numbers[:-1]
            ],
            default=0,
        )

        for previous in range(
            max(
                previous_structured + 1,
                number - 8,
                1,
            ),
            number,
        ):
            candidate = lines.get(
                previous,
                "",
            )

            if (
                not candidate
                or previous in consumed
                or _is_page_marker(
                    candidate
                )
                or _is_contact(
                    candidate
                )
                or _is_stop(
                    candidate
                )
                or ZERO_SECTION_RE.match(
                    candidate
                )
                or MONEY_RE.search(
                    candidate
                )
            ):
                continue

            if _letters(
                candidate
            ) >= 5:
                description_parts.append(
                    candidate
                )

        results.append({
            "strategy": (
                "TABLA_ARITMETICA"
            ),
            "pagina": pages.get(
                number,
                1,
            ),
            "linea_inicio": number,
            "linea_fin": number,
            "titulo": parsed[
                "titulo"
            ],
            "descripcion": " ".join(
                description_parts
            ),
            "cantidad": parsed[
                "cantidad"
            ],
            "unidad": parsed[
                "unidad"
            ],
            "precio_unitario": parsed[
                "precio_unitario"
            ],
            "importe": parsed[
                "importe"
            ],
            "alcance": "INCLUIDO",
            "confianza": "MUY_ALTA",
            "evidencia": line,
            "contexto": (
                current_section
            ),
        })

        consumed.add(number)

    exclusions = (
        _extract_exclusions(
            lines,
            pages,
        )
    )

    exclusion_ranges = set()

    for item in exclusions:
        exclusion_ranges.update(
            range(
                item["linea_inicio"],
                item["linea_fin"] + 1,
            )
        )

    money_lines = []

    for number, line in lines.items():
        if (
            number in consumed
            or number in exclusion_ranges
            or ZERO_SECTION_RE.match(
                line
            )
            or _is_stop(line)
            or _is_contact(line)
        ):
            continue

        if (
            MONEY_RE.search(line)
            and _letters(line) >= 5
        ):
            money_lines.append(
                number
            )

    for number in money_lines:
        line = lines[number]

        matches = list(
            MONEY_RE.finditer(
                line
            )
        )

        if not matches:
            continue

        amount = _money(
            matches[-1].group(0)
        )

        if amount is None:
            continue

        previous_money = (
            _previous_money_line(
                money_lines,
                number,
            )
        )

        start = (
            _amount_block_start(
                lines,
                number,
                previous_money,
            )
        )

        end = _amount_block_end(
            lines,
            number,
            money_lines,
        )

        parts = []

        for line_number in range(
            start,
            end + 1,
        ):
            value = lines.get(
                line_number,
                "",
            )

            if value:
                parts.append(value)

        if not parts:
            continue

        title = " ".join(parts)

        results.append({
            "strategy": (
                "IMPORTE_EN_BLOQUE"
            ),
            "pagina": pages.get(
                start,
                1,
            ),
            "linea_inicio": start,
            "linea_fin": end,
            "titulo": title,
            "descripcion": "",
            "cantidad": None,
            "unidad": "",
            "precio_unitario": None,
            "importe": amount,
            "alcance": "INCLUIDO",
            "confianza": "ALTA",
            "evidencia": title,
            "contexto": "",
        })

    occupied_ranges = set()

    # También proteger el fallback descriptivo:
    # las líneas del pie económico no deben
    # reaparecer como conceptos sin importe.
    occupied_ranges.update(
        economic_summary_lines
    )

    for item in results:
        occupied_ranges.update(
            range(
                item["linea_inicio"],
                item["linea_fin"] + 1,
            )
        )

    descriptive = (
        _extract_description_section_concepts(
            lines,
            pages,
            occupied_ranges,
            exclusion_ranges,
        )
    )

    results.extend(
        descriptive
    )

    results.extend(
        exclusions
    )

    results.sort(
        key=lambda item: (
            item["linea_inicio"],
            item["strategy"],
        )
    )

    return results


def _canonical_title(value):
    normalized = _norm(value)

    normalized = re.sub(
        r"[^A-Z0-9]+",
        " ",
        normalized,
    )

    return re.sub(
        r"\s+",
        " ",
        normalized,
    ).strip()


def _merge_layout_fallback(
    text_concepts,
    layout_concepts,
):
    # Si ya existen partidas tabulares económicamente
    # demostradas, no utilizamos layout para duplicarlas.
    arithmetic = [
        item
        for item in text_concepts
        if item["strategy"]
        == "TABLA_ARITMETICA"
    ]

    if arithmetic:
        return text_concepts

    existing = {
        _canonical_title(
            item["titulo"]
        )
        for item in text_concepts
        if item["alcance"]
        == "INCLUIDO"
    }

    merged = list(
        text_concepts
    )

    for item in layout_concepts:
        key = _canonical_title(
            item["titulo"]
        )

        if not key:
            continue

        if key in existing:
            continue

        merged.append(item)
        existing.add(key)

    merged.sort(
        key=lambda item: (
            item.get(
                "pagina",
                1,
            ),
            item.get(
                "linea_inicio",
                0,
            ),
            item["strategy"],
        )
    )

    return merged


def reconcile_concepts(
    concepts,
    base,
):
    base_value = (
        base
        if isinstance(
            base,
            Decimal,
        )
        else _money(base)
    )

    amounts = [
        item["importe"]
        for item in concepts
        if (
            item["alcance"]
            == "INCLUIDO"
            and item["importe"]
            is not None
            and item["importe"]
            > Decimal("0")
        )
    ]

    total = sum(
        amounts,
        Decimal("0"),
    )

    if base_value is None:
        status = "NO_DISPONIBLE"
        difference = None

    elif not amounts:
        status = "NO_VERIFICABLE"
        difference = None

    else:
        difference = (
            total - base_value
        )

        if abs(difference) <= Decimal(
            "0.02"
        ):
            status = "COMPLETA"

        elif difference < 0:
            status = "PARCIAL"

        else:
            status = "EXCEDE"

    return {
        "estado": status,
        "base": base_value,
        "suma_conceptos": total,
        "diferencia": difference,
        "conceptos_con_importe": len(
            amounts
        ),
    }


def extract_concepts_preview(
    *,
    text,
    base=None,
    pdf_path=None,
):
    text_concepts = (
        extract_text_concepts(
            text
        )
    )

    layout_concepts = []

    if pdf_path:
        try:
            layout_text = (
                extract_pdf_layout_text(
                    pdf_path
                )
            )

            layout_concepts = (
                extract_layout_table(
                    layout_text
                )
            )

        except (
            OSError,
            subprocess.SubprocessError,
        ):
            layout_concepts = []

    concepts = (
        _merge_layout_fallback(
            text_concepts,
            layout_concepts,
        )
    )

    reconciliation = (
        reconcile_concepts(
            concepts,
            base,
        )
    )

    return {
        "conceptos": concepts,
        "reconciliacion": (
            reconciliation
        ),
        "layout_usado": bool(
            layout_concepts
            and not any(
                item["strategy"]
                == "TABLA_ARITMETICA"
                for item
                in text_concepts
            )
        ),
    }
