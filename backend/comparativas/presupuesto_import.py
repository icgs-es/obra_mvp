# COMPARATIVAS_IMPORTACION_BASICA_PRESUPUESTO_V1

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import uuid

from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core import signing
from django.core.files import File
from django.db import transaction

from .models import (
    Comparativa,
    Ofertante,
)
from .services import (
    crear_oferta,
    guardar_documento,
)


STAGE_SALT = (
    "comparativas.importacion.presupuesto.v1"
)

STAGE_MAX_AGE = 3600

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".tif",
    ".tiff",
}


def _norm(value):
    value = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )

    value = "".join(
        ch
        for ch in value
        if not unicodedata.combining(ch)
    )

    value = value.upper()

    value = re.sub(
        r"[^A-Z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def _norm_tax(value):
    return "".join(
        ch
        for ch in str(value or "").upper()
        if ch.isalnum()
    )


def _lines(text):
    return [
        re.sub(r"\s+", " ", line).strip()
        for line in str(text or "").splitlines()
        if line.strip()
    ]


def _money(value):
    raw = str(value or "").strip()

    raw = (
        raw.replace("€", "")
        .replace("EUR", "")
        .replace(" ", "")
    )

    raw = re.sub(
        r"[^0-9,.\-]",
        "",
        raw,
    )

    if not raw:
        return None

    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = (
                raw.replace(".", "")
                .replace(",", ".")
            )
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(".", "")
        raw = raw.replace(",", ".")

    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _money_str(value):
    if value is None:
        return ""

    return str(
        value.quantize(
            Decimal("0.01")
        )
    )


MONEY_RE = re.compile(
    r"(?<!\d)"
    r"(-?"
    r"(?:\d{1,3}(?:\.\d{3})+,\d{2}"
    r"|\d{1,3}(?:,\d{3})+\.\d{2}"
    r"|\d+,\d{2}"
    r"|\d+\.\d{2})"
    r")"
    r"(?!\d)"
)


def _money_values(line):
    result = []

    for match in MONEY_RE.finditer(
        line or ""
    ):
        value = _money(
            match.group(1)
        )

        if value is not None:
            result.append(value)

    return result



def _find_dates(text):
    # COMPARATIVAS_PRESUPUESTO_IMAGE_MULTIPASS_R7
    #
    # Tolera OCR:
    # 14-08-2026
    # 14 - 08 - 2026
    # 14 / 08 / 2026
    found = []

    for match in re.finditer(
        r"\b([0-3]?\d)"
        r"\s*[/\-.]\s*"
        r"([01]?\d)"
        r"\s*[/\-.]\s*"
        r"((?:20)?\d{2})\b",
        text or "",
    ):
        day, month, year = (
            match.groups()
        )

        try:
            day = int(day)
            month = int(month)
            year = int(year)
        except ValueError:
            continue

        if year < 100:
            year += 2000

        if not (
            1 <= day <= 31
            and 1 <= month <= 12
            and 2020 <= year <= 2035
        ):
            continue

        value = (
            f"{year:04d}-"
            f"{month:02d}-"
            f"{day:02d}"
        )

        if value not in found:
            found.append(value)

    return found

def _find_document_date(text):
    # COMPARATIVAS_PRESUPUESTO_HEADER_GENERIC_R3
    lines = _lines(text)

    # Cabeceras tabulares OCR frecuentes:
    #
    # Fecha Valido hasta16/8/2026 16/9/2026
    #
    # El OCR puede pegar la primera fecha a la
    # etiqueta anterior y romper el \b usado por
    # _find_dates(). En una línea que contiene FECHA
    # tomamos la primera fecha numérica presente,
    # incluso si viene pegada a texto.
    loose_date_re = re.compile(
        r"(?<!\d)"
        r"([0-3]?\d)"
        r"\s*[/\-.]\s*"
        r"([01]?\d)"
        r"\s*[/\-.]\s*"
        r"((?:20)?\d{2})"
        r"(?!\d)"
    )

    for line in lines:
        if "FECHA" not in _norm(line):
            continue

        matches = list(
            loose_date_re.finditer(
                line
            )
        )

        if not matches:
            continue

        day, month, year = (
            matches[0].groups()
        )

        try:
            day = int(day)
            month = int(month)
            year = int(year)
        except ValueError:
            continue

        if year < 100:
            year += 2000

        if (
            1 <= day <= 31
            and 1 <= month <= 12
            and 2020 <= year <= 2035
        ):
            return (
                f"{year:04d}-"
                f"{month:02d}-"
                f"{day:02d}"
            )

    # 1. Fecha numérica en una línea
    # explícitamente etiquetada.
    for line in lines:
        if "FECHA" not in _norm(line):
            continue

        dates = _find_dates(line)

        if dates:
            return dates[0]

    # 2. Fecha española escrita:
    # "5 de agosto de 2026".
    months = {
        "ENERO": 1,
        "FEBRERO": 2,
        "MARZO": 3,
        "ABRIL": 4,
        "MAYO": 5,
        "JUNIO": 6,
        "JULIO": 7,
        "AGOSTO": 8,
        "SEPTIEMBRE": 9,
        "SETIEMBRE": 9,
        "OCTUBRE": 10,
        "NOVIEMBRE": 11,
        "DICIEMBRE": 12,
    }

    month_pattern = "|".join(
        months.keys()
    )

    for line in lines:
        normalized = _norm(line)

        match = re.search(
            rf"\b([0-3]?\d)"
            rf"\s+(?:DE\s+)?"
            rf"({month_pattern})"
            rf"\s+(?:DE\s+)?"
            rf"(20\d{{2}})\b",
            normalized,
            re.I,
        )

        if not match:
            continue

        day = int(match.group(1))
        month = months[
            match.group(2).upper()
        ]
        year = int(match.group(3))

        if not (
            1 <= day <= 31
            and 2020 <= year <= 2035
        ):
            continue

        return (
            f"{year:04d}-"
            f"{month:02d}-"
            f"{day:02d}"
        )

    # 3. Cualquier fecha numérica
    # válida del documento.
    dates = _find_dates(text)

    return dates[0] if dates else ""



def _is_valid_spanish_tax_id(value):
    """
    Valida controles de identificadores
    fiscales españoles antes de aceptar
    una coincidencia extraída por regex.

    Evita falsos positivos producidos por
    etiquetas o texto adyacente.

    Soporta:
      DNI/NIF   12345678Z
      NIE       X1234567L
      CIF       B12345678
    """
    value = _norm_tax(
        value
    )

    if not value:
        return False

    dni_letters = (
        "TRWAGMYFPDXBNJZSQVHLCKE"
    )

    # DNI / NIF de persona física.
    if re.fullmatch(
        r"\d{8}[A-Z]",
        value,
    ):
        number = int(
            value[:8]
        )

        expected = dni_letters[
            number % 23
        ]

        return (
            value[-1]
            == expected
        )

    # NIE.
    if re.fullmatch(
        r"[XYZ]\d{7}[A-Z]",
        value,
    ):
        prefixes = {
            "X": "0",
            "Y": "1",
            "Z": "2",
        }

        number = int(
            prefixes[value[0]]
            + value[1:8]
        )

        expected = dni_letters[
            number % 23
        ]

        return (
            value[-1]
            == expected
        )

    # CIF de persona jurídica / entidad.
    if re.fullmatch(
        r"[ABCDEFGHJNPQRSUVW]"
        r"\d{7}[0-9A-J]",
        value,
    ):
        digits = value[1:8]

        even_sum = sum(
            int(digit)
            for digit
            in digits[1::2]
        )

        odd_sum = 0

        for digit in digits[0::2]:
            doubled = (
                int(digit) * 2
            )

            odd_sum += (
                doubled // 10
                + doubled % 10
            )

        control_number = (
            10
            - (
                (
                    even_sum
                    + odd_sum
                )
                % 10
            )
        ) % 10

        control_letter = (
            "JABCDEFGHI"[
                control_number
            ]
        )

        return (
            value[-1]
            in (
                str(control_number),
                control_letter,
            )
        )

    return False


def _find_tax_ids(text):
    """
    Extracción fiscal tolerante a puntos,
    espacios y guiones, seguida siempre de
    validación del dígito/letra de control.

    Ejemplos:
      B-29.707.536 -> B29707536
      11.943.051-W -> 11943051W

    Un fragmento sintácticamente parecido
    pero fiscalmente inválido se descarta.
    """
    found = []

    patterns = (
        # DNI / NIF.
        r"\b("
        r"(?:\d[\s.\-]*){8}"
        r"[A-Z]"
        r")\b",

        # NIE.
        r"\b("
        r"[XYZ]"
        r"(?:[\s.\-]*\d){7}"
        r"[\s.\-]*[A-Z]"
        r")\b",

        # CIF.
        r"\b("
        r"[ABCDEFGHJNPQRSUVW]"
        r"(?:[\s.\-]*\d){7}"
        r"[\s.\-]*[0-9A-J]"
        r")\b",
    )

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            text or "",
            re.I,
        ):
            value = _norm_tax(
                match.group(1)
            )

            if not (
                _is_valid_spanish_tax_id(
                    value
                )
            ):
                continue

            if (
                value
                and value not in found
            ):
                found.append(
                    value
                )

    return found

def _find_reference(text):
    # COMPARATIVAS_PRESUPUESTO_REFERENCE_FAIL_CLOSED_R4
    lines = _lines(text)

    # Identificadores fiscales presentes en el
    # documento. Nunca pueden convertirse en
    # referencia de presupuesto.
    tax_ids = {
        _norm_tax(value)
        for value in _find_tax_ids(text)
        if value
    }

    # Prioridad máxima: referencia explícita en
    # la misma línea de PRESUPUESTO.
    #
    # Tolera OCR:
    #   PRESUPUESTO N* 26-047
    #   PRESUPUESTO Nº 26/26069
    #   PRESUPUESTO) $ 126069
    #
    # Es preferible conservar una referencia OCR
    # imperfecta asociada a la etiqueta documental
    # que capturar después una especificación técnica.
    explicit_budget_re = re.compile(
        r"\bPRESUPUESTO\b"
        r"\s*"
        r"(?:"
        r"N"
        r"(?:[ºO°*.]|E\.)?"
        r"\s*"
        r")?"
        r"[:#$()\-.*\s]*"
        r"([A-Z0-9]"
        r"[A-Z0-9/_\-.]{2,})",
        re.I,
    )

    technical_reference_re = re.compile(
        r"^\d{1,2}P/"
        r"\d{1,3}A/"
        r"\d{1,3}MA$",
        re.I,
    )

    for line in lines[:60]:
        match = explicit_budget_re.search(
            line
        )

        if not match:
            continue

        candidate = (
            match.group(1)
            .strip(" .,:;|")
        )

        if not re.search(
            r"\d",
            candidate,
        ):
            continue

        if (
            _norm_tax(candidate)
            in tax_ids
        ):
            continue

        if technical_reference_re.fullmatch(
            candidate
        ):
            continue

        # Una cantidad monetaria pura no es una
        # referencia documental.
        if (
            re.fullmatch(
                r"\d{1,3}(?:[.,]\d{3})+",
                candidate,
            )
        ):
            continue

        return candidate

    # 1. Formas explícitas donde etiqueta y
    # referencia aparecen en la misma línea.
    patterns = [
        (
            r"(?:N[ºO°]?\s*(?:DE\s*)?"
            r"PRESUPUESTO"
            r"|PRESUPUESTO\s*"
            r"(?:N[ºO°]?|NUM(?:ERO)?|"
            r"REF(?:ERENCIA)?)?)"
            r"\s*[:#\-]?\s*"
            r"([A-Z0-9]"
            r"[A-Z0-9/_\-.]{2,})"
        ),
        (
            r"(?:OFERTA|COTIZACI[ÓO]N)"
            r"\s*(?:N[ºO°]?|NUM(?:ERO)?|"
            r"REF(?:ERENCIA)?)?"
            r"\s*[:#\-]?\s*"
            r"([A-Z0-9]"
            r"[A-Z0-9/_\-.]{2,})"
        ),
        (
            r"(?:N[ºO°]?\s*)?"
            r"ESTUDIO"
            r"\s*[:#\-]?\s*"
            r"([A-Z0-9]"
            r"[A-Z0-9/_\-.]{2,})"
        ),
    ]

    for line in lines:
        for pattern in patterns:
            match = re.search(
                pattern,
                line,
                re.I,
            )

            if not match:
                continue

            candidate = (
                match.group(1)
                .strip(" .,:;|")
            )

            normalized_candidate = (
                _norm_tax(candidate)
            )

            if (
                normalized_candidate
                in tax_ids
            ):
                continue

            if not re.search(
                r"\d",
                candidate,
            ):
                continue

            return candidate

    # 2. Cabecera tabular real:
    #
    # Nº ESTUDIO Fecha Página
    # 2026-ES.60 5 de agosto de 2026 1 / 1
    #
    # No basta con encontrar la palabra
    # ESTUDIO aislada. Debe existir además
    # una señal de cabecera documental.
    document_tokens = (
        "ESTUDIO",
        "PRESUPUESTO",
        "OFERTA",
        "COTIZACION",
    )

    header_tokens = (
        "FECHA",
        "PAGINA",
        "REFERENCIA",
        "NUMERO",
    )

    skip_tokens = {
        "ESTUDIO",
        "PRESUPUESTO",
        "OFERTA",
        "COTIZACION",
        "FECHA",
        "PAGINA",
        "REFERENCIA",
        "NUMERO",
    }

    for index, line in enumerate(lines):
        normalized = _norm(line)

        has_document_label = any(
            token in normalized
            for token in document_tokens
        )

        has_header_signal = any(
            token in normalized
            for token in header_tokens
        )

        if not (
            has_document_label
            and has_header_signal
        ):
            continue

        # Solo líneas POSTERIORES a la
        # cabecera. Nunca miramos hacia
        # atrás, evitando capturar DNI/CIF
        # de la cabecera fiscal.
        # COMPARATIVAS_PRESUPUESTO_REFERENCE_HEADER_WINDOW_R5
        #
        # Algunos presupuestos intercalan cliente,
        # obra y dirección entre la cabecera
        # "Nº ESTUDIO / Fecha / Página" y la fila
        # donde aparece la referencia documental.
        #
        # La búsqueda sigue siendo solo hacia
        # delante y conserva todos los filtros
        # fail-closed de DNI/CIF, fechas y tokens.
        for candidate_line in lines[
            index + 1:index + 10
        ]:
            tokens = re.findall(
                r"\b[A-Z0-9]"
                r"[A-Z0-9/_\-.]{2,}\b",
                candidate_line.upper(),
            )

            for token in tokens:
                clean = token.strip(
                    " .,:;|"
                )

                normalized_clean = (
                    _norm_tax(clean)
                )

                if not normalized_clean:
                    continue

                if normalized_clean in tax_ids:
                    continue

                if (
                    _norm(clean)
                    in skip_tokens
                ):
                    continue

                if not re.search(
                    r"\d",
                    clean,
                ):
                    continue

                # Una fecha no es referencia.
                if re.fullmatch(
                    r"\d{1,2}"
                    r"[/\-.]"
                    r"\d{1,2}"
                    r"[/\-.]"
                    r"\d{2,4}",
                    clean,
                ):
                    continue

                # Fallback deliberadamente
                # conservador: la referencia
                # tabular debe incorporar un
                # separador documental.
                if not re.search(
                    r"[/\-.]",
                    clean,
                ):
                    continue

                return clean

    return ""

def _contains_normalized_label(
    normalized,
    label,
):
    normalized = (
        " "
        + _norm(normalized)
        + " "
    )

    label = _norm(label)

    if not label:
        return False

    return (
        " " + label + " "
        in normalized
    )


def _find_labeled_amount(
    text,
    *,
    labels,
    exclude=(),
):
    for line in _lines(text):
        normalized = _norm(line)

        if any(
            _contains_normalized_label(
                normalized,
                item,
            )
            for item in exclude
        ):
            continue

        if not any(
            _contains_normalized_label(
                normalized,
                item,
            )
            for item in labels
        ):
            continue

        values = _money_values(
            line
        )

        if values:
            return values[-1]

    return None


def _economic_markers(
    value,
):
    normalized = (
        " "
        + _norm(value)
        + " "
    )

    has_total = (
        " TOTAL "
        in normalized
        or " TOTAL PRESUPUESTO "
        in normalized
        or " IMPORTE TOTAL "
        in normalized
    )

    has_tax = (
        " IVA "
        in normalized
        or " I V A "
        in normalized
        or " CUOTA "
        in normalized
        or " LVA "
        in normalized
        or " VAG "
        in normalized
    )

    has_base = (
        " BASE "
        in normalized
        or " BASE IMPONIBLE "
        in normalized
        or " BASE I V A "
        in normalized
        or normalized.lstrip().startswith(
            "IMPORTE "
        )
    )

    return (
        has_base,
        has_tax,
        has_total,
    )


def _reconciled_triplet_from_values(
    values,
):
    candidates = []

    for first_index in range(
        len(values)
    ):
        for second_index in range(
            first_index + 1,
            len(values),
        ):
            first = values[
                first_index
            ]

            second = values[
                second_index
            ]

            subtotal = (
                first + second
            )

            for total_index, total in enumerate(
                values
            ):
                if total_index in (
                    first_index,
                    second_index,
                ):
                    continue

                if (
                    total < first
                    or total < second
                ):
                    continue

                if (
                    abs(
                        subtotal
                        - total
                    )
                    > Decimal("0.05")
                ):
                    continue

                base = max(
                    first,
                    second,
                )

                iva = min(
                    first,
                    second,
                )

                if (
                    base <= 0
                    or iva < 0
                ):
                    continue

                ratio = (
                    iva / base
                    if base
                    else Decimal("0")
                )

                # IVA/tributos habituales.
                # No se restringe a 21%.
                if (
                    iva > 0
                    and not (
                        Decimal("0.01")
                        <= ratio
                        <= Decimal("0.40")
                    )
                ):
                    continue

                candidates.append(
                    (
                        total,
                        base,
                        iva,
                    )
                )

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda item: item[0],
    )


def _find_reconciled_economic_block(
    text,
):
    lines = _lines(text)

    for index in range(
        len(lines)
    ):
        for size in (
            1,
            2,
            3,
            4,
        ):
            window = lines[
                index:index + size
            ]

            if not window:
                continue

            combined = " ".join(
                window
            )

            (
                has_base,
                has_tax,
                has_total,
            ) = _economic_markers(
                combined
            )

            if not (
                has_base
                and has_tax
                and has_total
            ):
                continue

            values = []

            for item in window:
                values.extend(
                    _money_values(
                        item
                    )
                )

            if len(values) < 3:
                continue

            triplet = (
                _reconciled_triplet_from_values(
                    values
                )
            )

            if triplet is None:
                continue

            total, base, iva = (
                triplet
            )

            return {
                "base": (
                    _money_str(base)
                ),
                "iva": (
                    _money_str(iva)
                ),
                "total": (
                    _money_str(total)
                ),
            }

    return {
        "base": "",
        "iva": "",
        "total": "",
    }


def _has_degraded_economic_block(
    text,
):
    for line in _lines(text):
        (
            has_base,
            has_tax,
            has_total,
        ) = _economic_markers(
            line
        )

        if not (
            has_base
            and has_tax
            and has_total
        ):
            continue

        values = _money_values(
            line
        )

        if len(values) < 2:
            continue

        if (
            _reconciled_triplet_from_values(
                values
            )
            is None
        ):
            return True

    return False



def _find_summary_totals(text):
    """
    Detecta bloques documentales del tipo
    RESUMEN DE IMPORTES aunque PDF/OCR
    altere el orden visual de etiquetas.

    No presupone proveedor ni plantilla.

    Solo devuelve base/IVA/total cuando
    existe una combinación matemática:

        base + cuota_iva ~= total
    """
    lines = _lines(text)

    for index, line in enumerate(lines):
        normalized = _norm(line)

        if (
            "RESUMEN DE IMPORTES"
            not in normalized
        ):
            continue

        window = lines[
            index:index + 14
        ]

        combined = " ".join(
            _norm(item)
            for item in window
        )

        required = (
            "BASE IMPONIBLE",
            "IVA",
            "TOTAL",
        )

        if not all(
            token in combined
            for token in required
        ):
            continue

        values = []

        for item in window:
            values.extend(
                _money_values(
                    item
                )
            )

        if len(values) < 3:
            continue

        candidates = []

        for first_index in range(
            len(values)
        ):
            for second_index in range(
                first_index + 1,
                len(values),
            ):
                first = values[
                    first_index
                ]

                second = values[
                    second_index
                ]

                subtotal = (
                    first + second
                )

                for total_index, total in enumerate(
                    values
                ):
                    if total_index in (
                        first_index,
                        second_index,
                    ):
                        continue

                    if (
                        total < first
                        or total < second
                    ):
                        continue

                    if (
                        abs(
                            subtotal - total
                        )
                        > Decimal("0.05")
                    ):
                        continue

                    base = max(
                        first,
                        second,
                    )

                    iva = min(
                        first,
                        second,
                    )

                    candidates.append(
                        (
                            total,
                            base,
                            iva,
                        )
                    )

        if not candidates:
            continue

        # Si hubiera más de una combinación
        # coherente, el total documental
        # principal será el de mayor importe.
        total, base, iva = max(
            candidates,
            key=lambda item: item[0],
        )

        return {
            "base": _money_str(base),
            "iva": _money_str(iva),
            "total": _money_str(total),
        }

    return {
        "base": "",
        "iva": "",
        "total": "",
    }


def _find_totals(text):
    reconciled = (
        _find_reconciled_economic_block(
            text
        )
    )

    if (
        reconciled.get("base")
        and reconciled.get("iva")
        and reconciled.get("total")
    ):
        return reconciled

    summary = _find_summary_totals(
        text
    )

    if (
        summary.get("base")
        and summary.get("iva")
        and summary.get("total")
    ):
        return summary

    degraded_block = (
        _has_degraded_economic_block(
            text
        )
    )

    base = _find_labeled_amount(
        text,
        labels=(
            "BASE IMPONIBLE",
            "BASE IVA",
            "BASE I V A",
            "SUBTOTAL",
        ),
    )

    iva = _find_labeled_amount(
        text,
        labels=(
            "CUOTA IVA",
            "CUOTA I V A",
            "IVA",
            "IMPUESTOS",
        ),
    )

    total = _find_labeled_amount(
        text,
        labels=(
            "TOTAL PRESUPUESTO",
            "IMPORTE TOTAL",
            "TOTAL",
        ),
        exclude=(
            "SUBTOTAL",
        ),
    )

    lines = _lines(text)

    if total is None:
        for index, line in enumerate(
            lines
        ):
            normalized = _norm(
                line
            )

            is_total_label = (
                normalized == "TOTAL"
                or normalized.startswith(
                    "TOTAL "
                )
                or normalized
                == "TOTAL PRESUPUESTO"
            )

            if not is_total_label:
                continue

            footer_values = []

            for candidate in lines[
                index:index + 4
            ]:
                footer_values.extend(
                    _money_values(
                        candidate
                    )
                )

            if not footer_values:
                continue

            total = footer_values[-1]

            previous = " ".join(
                _norm(value)
                for value in lines[
                    max(0, index - 3):
                    index
                ]
            )

            if (
                base is None
                and "BASE IMPONIBLE"
                in previous
                and len(
                    footer_values
                ) >= 2
            ):
                base = (
                    footer_values[0]
                )

            break

    if (
        base is None
        and total is not None
    ):
        for index, line in enumerate(
            lines
        ):
            normalized = _norm(
                line
            )

            if not (
                "BASE IMPONIBLE"
                in normalized
                or "BASE IVA"
                in normalized
                or "BASE I V A"
                in normalized
            ):
                continue

            values = []

            for candidate in lines[
                index + 1:index + 6
            ]:
                values.extend(
                    _money_values(
                        candidate
                    )
                )

            if len(values) >= 2:
                base = values[0]
                break

    if (
        total is None
        and base is not None
        and iva is not None
    ):
        total = base + iva

    if (
        base is not None
        and iva is not None
        and total is not None
    ):
        if (
            abs(
                (
                    base
                    + iva
                )
                - total
            )
            > Decimal("0.05")
        ):
            # Una cabecera completa pero
            # matemáticamente imposible no
            # puede precargar valores.
            return {
                "base": "",
                "iva": "",
                "total": "",
            }

    # Si el OCR contiene explícitamente un bloque
    # BASE/IVA/TOTAL degradado y no hemos podido
    # reconciliarlo, no aceptamos un importe
    # aislado como 37,92 como "total".
    if degraded_block:
        if not (
            base is not None
            and iva is not None
            and total is not None
            and abs(
                (base + iva)
                - total
            )
            <= Decimal("0.05")
        ):
            return {
                "base": "",
                "iva": "",
                "total": "",
            }

    return {
        "base": _money_str(base),
        "iva": _money_str(iva),
        "total": _money_str(total),
    }


# COMPARATIVAS_PRESUPUESTO_SUPPLIER_CLEAN_R6

def _is_extractor_technical_line(line):
    """
    Descarta marcas internas creadas por la
    extracción PDF/OCR. Nunca son contenido
    documental ni nombre de proveedor.
    """
    normalized = _norm(line)

    if not normalized:
        return True

    patterns = (
        r"^PAGE\s+\d+$",
        r"^PAGE\s+\d+\s+OCR$",
        r"^PAGE\s+\d+\s+OCR\s+ERROR.*$",
        r"^OCR\s+ERROR.*$",
    )

    return any(
        re.match(
            pattern,
            normalized,
            re.I,
        )
        for pattern in patterns
    )


def _clean_supplier_candidate_line(line):
    """
    Limpieza conservadora de una posible
    razón social/nombre.

    Caso genérico frecuente:
      EMPRESA / PERSONA  FECHA: 13/08/2026

    Conserva solo el texto anterior a la
    etiqueta FECHA. No elimina palabras
    arbitrarias del nombre.
    """
    line = re.sub(
        r"\s+",
        " ",
        str(line or ""),
    ).strip()

    if (
        not line
        or _is_extractor_technical_line(
            line
        )
    ):
        return ""

    # Eliminar únicamente un sufijo de
    # fecha documental claramente etiquetado.
    line = re.sub(
        r"\s+FECHA"
        r"\s*[:\-]?\s*"
        r"[0-3]?\d"
        r"[/\-.]"
        r"[01]?\d"
        r"[/\-.]"
        r"(?:20)?\d{2}"
        r"\s*$",
        "",
        line,
        flags=re.I,
    ).strip()

    return line



def _plausible_name_line(line):
    raw = str(
        line or ""
    ).strip()

    if not raw:
        return False

    raw_lower = raw.lower()

    # Un dominio/correo degradado por OCR
    # tampoco es una razón social:
    #   electricidadOmarca94.com
    #
    # Si además existe un sufijo societario
    # explícito, no aplicamos este descarte.
    has_domain_fragment = bool(
        re.search(
            r"\."
            r"(?:com|es|net|org|eu)"
            r"\b",
            raw,
            re.I,
        )
    )

    has_legal_suffix = bool(
        re.search(
            r"\b(?:"
            r"S\.?\s*L\.?|"
            r"S\.?\s*A\.?|"
            r"S\.?\s*L\.?\s*U\.?"
            r")\b",
            raw,
            re.I,
        )
    )

    if (
        has_domain_fragment
        and not has_legal_suffix
    ):
        return False

    # Web, email y URLs no son razón social.
    if any(
        marker in raw_lower
        for marker in (
            "@",
            "www.",
            "http://",
            "https://",
        )
    ):
        return False

    # Contacto telefónico al comienzo de línea.
    # Tolera abreviaturas y OCR:
    # Mv., Móvil, Teléf., Telf., Tlf., Fax...
    if re.match(
        r"^\s*(?:"
        r"e[\s.\-]*mail|"
        r"email|"
        r"correo|"
        r"internet|"
        r"web|"
        r"tel[eé]fono|"
        r"tel[eé]f|"
        r"telef|"
        r"telfs?|"
        r"tlf|"
        r"mv|"
        r"m[oó]vil|"
        r"movil|"
        r"fax"
        r")\s*[:.]?",
        raw,
        re.I,
    ):
        return False

    normalized_raw = (
        " "
        + _norm(raw)
        + " "
    )

    # Una dirección contaminada no puede
    # convertirse en proveedor.
    address_tokens = (
        " C/ ",
        " CALLE ",
        " AV ",
        " AVD ",
        " AVDA ",
        " AVENIDA ",
        " PLAZA ",
        " CTRA ",
        " CARRETERA ",
        " CAMINO ",
    )

    if (
        any(
            token in normalized_raw
            for token in address_tokens
        )
        and re.search(
            r"\d",
            raw,
        )
    ):
        return False

    # Dirección postal sin prefijo C/, Avda.,
    # etc. Ejemplo genérico:
    #   Nombre de calle, 14 · 49007 CIUDAD
    #
    # La presencia de un CP español de cinco
    # dígitos es señal suficiente para no usar
    # toda esa línea como razón social.
    if re.search(
        r"\b\d{5}\b",
        raw,
    ):
        return False

    line = (
        _clean_supplier_candidate_line(
            raw
        )
    )

    normalized = _norm(
        line
    )

    if not normalized:
        return False

    if (
        len(line) < 4
        or len(line) > 120
    ):
        return False

    bad = (
        "PRESUPUESTO",
        "CLIENTE",
        "DESTINATARIO",
        "DIRECCION",
        "DOMICILIO",
        "TELEFONO",
        "EMAIL",
        "E MAIL",
        "CORREO",
        "INTERNET",
        "FAX",
        "FECHA",
        "TOTAL",
        "BASE IMPONIBLE",
        "IVA",
        "IBAN",
        "CUENTA",
        "HOJA ",
        "PAGINA ",
        "PAGE ",
        "OCR ",
    )

    if any(
        token in normalized
        for token in bad
    ):
        return False

    letters = sum(
        1
        for char in line
        if char.isalpha()
    )

    if letters < 4:
        return False

    return True



def _guess_supplier_name(
    text,
    tax_ids,
):
    lines = _lines(text)

    normalized_tax_ids = {
        _norm_tax(value)
        for value in tax_ids
    }

    # Prioridad principal:
    # si encontramos un NIF/CIF, inspeccionar
    # las líneas inmediatamente anteriores.
    # Es una estructura muy habitual:
    #
    # EMPRESA / PERSONA   FECHA: ...
    # NIF: ...
    #
    # Las marcas PAGE/OCR se descartan.
    for index, line in enumerate(
        lines[:40]
    ):
        compact = _norm_tax(line)

        if not any(
            tax
            and tax in compact
            for tax in normalized_tax_ids
        ):
            continue

        for candidate_index in range(
            index - 1,
            max(-1, index - 9),
            -1,
        ):
            raw_candidate = lines[
                candidate_index
            ]

            candidate = (
                _clean_supplier_candidate_line(
                    raw_candidate
                )
            )

            if (
                candidate
                and _plausible_name_line(
                    candidate
                )
            ):
                return candidate

    # Segundo nivel: razones sociales o
    # denominaciones con vocabulario
    # empresarial reconocible.
    business_tokens = (
        " S L",
        " SL ",
        " S A",
        " SA ",
        "INSTALACIONES",
        "FONTANERIA",
        "FONTANERÍA",
        "ELECTRICIDAD",
        "CONSTRUCCIONES",
        "SERVICIOS",
        "MATERIALES",
        "SUMINISTROS",
        "REFORMAS",
    )

    for raw_line in lines[:40]:
        candidate = (
            _clean_supplier_candidate_line(
                raw_line
            )
        )

        if not candidate:
            continue

        normalized = (
            " "
            + _norm(candidate)
            + " "
        )

        if (
            _plausible_name_line(
                candidate
            )
            and any(
                token in normalized
                for token in business_tokens
            )
        ):
            return candidate

    return ""

def match_providers(
    *,
    text,
    tax_ids,
    candidate_name,
    providers,
):
    normalized_text = _norm(text)

    tax_set = {
        _norm_tax(value)
        for value in tax_ids
        if value
    }

    exact_tax = []

    for provider in providers or []:
        provider_tax = _norm_tax(
            provider.get("cif")
        )

        if (
            provider_tax
            and provider_tax in tax_set
        ):
            exact_tax.append(
                provider
            )

    if exact_tax:
        confidence = (
            "MUY_ALTA"
            if len(exact_tax) == 1
            else "REVISAR"
        )

        return [
            {
                **provider,
                "confidence": confidence,
                "reason": (
                    "CIF/NIF exacto"
                    if len(exact_tax) == 1
                    else (
                        "CIF/NIF exacto con "
                        "más de una coincidencia"
                    )
                ),
            }
            for provider in exact_tax[:5]
        ]

    exact_name = []

    for provider in providers or []:
        names = [
            provider.get(
                "nombre_comercial"
            ),
            provider.get(
                "nombre_fiscal"
            ),
        ]

        for name in names:
            normalized_name = _norm(
                name
            )

            if (
                len(normalized_name) >= 8
                and normalized_name
                in normalized_text
            ):
                exact_name.append(
                    provider
                )
                break

    if exact_name:
        return [
            {
                **provider,
                "confidence": (
                    "ALTA"
                    if len(exact_name) == 1
                    else "REVISAR"
                ),
                "reason": (
                    "Nombre completo localizado "
                    "en el documento"
                ),
            }
            for provider in exact_name[:5]
        ]

    normalized_candidate = _norm(
        candidate_name
    )

    if len(normalized_candidate) >= 8:
        candidate_matches = []

        for provider in providers or []:
            names = [
                provider.get(
                    "nombre_comercial"
                ),
                provider.get(
                    "nombre_fiscal"
                ),
            ]

            for name in names:
                normalized_name = _norm(
                    name
                )

                if (
                    normalized_name
                    and (
                        normalized_name
                        == normalized_candidate
                    )
                ):
                    candidate_matches.append(
                        provider
                    )
                    break

        if candidate_matches:
            return [
                {
                    **provider,
                    "confidence": "ALTA",
                    "reason": (
                        "Nombre normalizado exacto"
                    ),
                }
                for provider
                in candidate_matches[:5]
            ]

    return []



def analizar_texto_presupuesto(
    text,
    providers,
):
    tax_ids = _find_tax_ids(text)

    candidate_name = (
        _guess_supplier_name(
            text,
            tax_ids,
        )
    )

    matches = match_providers(
        text=text,
        tax_ids=tax_ids,
        candidate_name=candidate_name,
        providers=providers,
    )

    # Canonización exclusivamente cuando
    # existe UNA coincidencia exacta de
    # identidad fiscal dentro del ámbito
    # de proveedores recibido.
    #
    # No vincula automáticamente:
    # únicamente mejora la información
    # mostrada para revisión humana.
    if matches:
        top_match = matches[0]

        if (
            top_match.get(
                "confidence"
            )
            == "MUY_ALTA"
            and top_match.get(
                "reason"
            )
            == "CIF/NIF exacto"
        ):
            master_name = (
                top_match.get(
                    "nombre_comercial"
                )
                or top_match.get(
                    "nombre_fiscal"
                )
                or ""
            )

            master_tax = _norm_tax(
                top_match.get(
                    "cif"
                )
                or ""
            )

            if master_name:
                candidate_name = (
                    master_name
                )

            if master_tax:
                tax_ids = [
                    master_tax
                ]

    totals = _find_totals(text)

    detected = {
        "proveedor_nombre": (
            candidate_name
        ),
        "nif_cif_candidates": (
            tax_ids
        ),
        "numero_documento": (
            _find_reference(text)
        ),
        "fecha": (
            _find_document_date(text)
        ),
        "base_imponible": (
            totals["base"]
        ),
        "iva": totals["iva"],
        "total": totals["total"],
    }

    confidence = "REVISAR"

    if matches:
        confidence = matches[0][
            "confidence"
        ]

    return {
        "detected": detected,
        "provider_matches": matches,
        "confidence": confidence,
    }

def _run_tesseract(
    path,
    *,
    psm,
    timeout=120,
):
    proc = subprocess.run(
        [
            "tesseract",
            str(path),
            "stdout",
            "-l",
            "spa+eng",
            "--psm",
            str(psm),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )

    return {
        "ok": proc.returncode == 0,
        "text": proc.stdout or "",
        "error": (
            ""
            if proc.returncode == 0
            else (proc.stderr or "")[:1000]
        ),
        "psm": psm,
    }



def _ocr_text_quality(text):
    """
    COMPARATIVAS_PRESUPUESTO_OCR_IDENTITY_QUALITY_R8

    Puntuación documental genérica.

    Además de detectar que existe un
    presupuesto, fecha, totales, etc.,
    valora la calidad de la identidad
    asociada al NIF/CIF.

    No contiene proveedores concretos.
    """
    normalized = _norm(text)

    score = 0

    tax_ids = _find_tax_ids(
        text
    )

    if tax_ids:
        score += 6

    if _find_document_date(text):
        score += 5

    if "PRESUPUESTO" in normalized:
        score += 4

    if "FECHA" in normalized:
        score += 2

    if "BASE IMPONIBLE" in normalized:
        score += 3

    if "CUOTA IVA" in normalized:
        score += 2

    if "TOTAL" in normalized:
        score += 3

    if len(text.strip()) >= 500:
        score += 1

    # Calidad de identidad:
    #
    # si existe NIF/CIF, intentamos obtener
    # el nombre asociado utilizando exactamente
    # el mismo detector genérico que luego usa
    # el importador.
    #
    # Entre dos OCR documentalmente equivalentes,
    # preferimos aquel que conserva un nombre
    # más completo junto a la identidad fiscal.
    supplier_name = ""

    if tax_ids:
        supplier_name = (
            _guess_supplier_name(
                text,
                tax_ids,
            )
            or ""
        )

    supplier_tokens = [
        token
        for token in _norm(
            supplier_name
        ).split()
        if (
            len(token) >= 2
            and not token.isdigit()
        )
    ]

    supplier_token_count = min(
        len(supplier_tokens),
        6,
    )

    if supplier_name:
        score += 3

    score += supplier_token_count

    # Desempates:
    #
    # 1. nombre asociado a NIF/CIF más completo;
    # 2. cantidad de texto útil.
    #
    # La longitud total nunca domina sobre
    # una identidad mejor reconstruida.
    tie_break = min(
        len(text),
        5000,
    )

    return (
        score,
        supplier_token_count,
        tie_break,
    )

def _find_footer_totals(text):
    """
    Extrae únicamente un bloque de totales
    inequívoco.

    Requiere cabecera BASE IMPONIBLE y busca
    importes próximos. Si aparecen base,
    cuota y total, la cuota IVA solo se
    acepta si:

        base + cuota ~= total

    Esto rechaza OCR degradado como:
        6890 + 146,90 != 8336,90
    """
    lines = _lines(text)

    for index, line in enumerate(lines):
        normalized = _norm(line)

        if (
            "BASE IMPONIBLE"
            not in normalized
        ):
            continue

        window = lines[
            index:index + 6
        ]

        combined = " ".join(
            _norm(item)
            for item in window
        )

        if "TOTAL" not in combined:
            continue

        values = []

        for item in window:
            values.extend(
                _money_values(item)
            )

        if len(values) < 2:
            continue

        base = values[0]
        total = values[-1]
        iva = None

        if (
            "IVA" in combined
            or "CUOTA IVA"
            in combined
        ):
            for candidate in values[
                1:-1
            ]:
                difference = abs(
                    (
                        base
                        + candidate
                    )
                    - total
                )

                if (
                    difference
                    <= Decimal("0.05")
                ):
                    iva = candidate
                    break

        return {
            "base": _money_str(base),
            "iva": _money_str(iva),
            "total": _money_str(total),
        }

    return {
        "base": "",
        "iva": "",
        "total": "",
    }


def _footer_quality(result):
    score = 0

    base = result.get("base") or ""
    iva = result.get("iva") or ""
    total = result.get("total") or ""

    if base:
        score += 3

    if total:
        score += 3

    if iva:
        score += 5

    return score


def _prepare_image_for_ocr(
    source,
    target,
):
    from PIL import (
        Image,
        ImageOps,
    )

    with Image.open(source) as image:
        image.load()

        image = ImageOps.exif_transpose(
            image
        )

        # Se conserva color/estructura del
        # original. El diagnóstico real
        # mostró que el escalado forzado no
        # mejora de forma consistente.
        image.save(
            target,
            format="PNG",
        )


def _extract_image_text(path):
    """
    OCR multipase genérico.

    PSM 3: segmentación automática.
    PSM 6: bloque uniforme.
    PSM 11: texto disperso.

    Se elige por señales documentales, no
    por proveedor.
    """
    if not shutil.which("tesseract"):
        return {
            "ok": False,
            "text": "",
            "method": "",
            "ocr_used": False,
            "error": (
                "tesseract no disponible"
            ),
            "candidates": [],
        }

    try:
        with tempfile.TemporaryDirectory(
            prefix="cmp_presupuesto_ocr_r7_"
        ) as tmp:
            normalized_path = (
                Path(tmp)
                / "document.png"
            )

            _prepare_image_for_ocr(
                path,
                normalized_path,
            )

            candidates = []

            for psm in (
                3,
                6,
                11,
            ):
                result = _run_tesseract(
                    normalized_path,
                    psm=psm,
                )

                if not result["ok"]:
                    continue

                text = (
                    result.get("text")
                    or ""
                )

                if not text.strip():
                    continue

                quality = (
                    _ocr_text_quality(
                        text
                    )
                )

                candidates.append({
                    **result,
                    "quality": quality,
                })

            if not candidates:
                return {
                    "ok": False,
                    "text": "",
                    "method": (
                        "image_tesseract_failed"
                    ),
                    "ocr_used": True,
                    "error": (
                        "Tesseract no produjo "
                        "texto útil."
                    ),
                    "candidates": [],
                }

            candidates.sort(
                key=lambda item: (
                    item["quality"][0],
                    item["quality"][1],
                    item["quality"][2],
                ),
                reverse=True,
            )

            best = candidates[0]

            return {
                "ok": True,
                "text": (
                    best["text"]
                ),
                "method": (
                    "image_tesseract_"
                    f"psm{best['psm']}"
                ),
                "ocr_used": True,
                "error": "",
                "selected_psm": (
                    best["psm"]
                ),
                "candidates": [
                    {
                        "psm": item["psm"],
                        "quality": (
                            item["quality"]
                        ),
                        "text_len": len(
                            item["text"]
                        ),
                    }
                    for item
                    in candidates
                ],
            }

    except Exception as exc:
        return {
            "ok": False,
            "text": "",
            "method": (
                "image_ocr_error"
            ),
            "ocr_used": True,
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
            "candidates": [],
        }


def _extract_image_footer_text(path):
    """
    Fallback genérico de pie documental.

    Solo se usa cuando faltan importes
    principales tras el OCR de página
    completa.

    Se analiza el 32% inferior de la imagen
    con varios PSM y se conserva el resultado
    económicamente más coherente.
    """
    from PIL import (
        Image,
        ImageOps,
    )

    if not shutil.which("tesseract"):
        return {
            "ok": False,
            "text": "",
            "method": "",
            "totals": {
                "base": "",
                "iva": "",
                "total": "",
            },
        }

    try:
        with tempfile.TemporaryDirectory(
            prefix="cmp_presupuesto_footer_r7_"
        ) as tmp:
            tmp = Path(tmp)

            crop_path = (
                tmp / "footer.png"
            )

            with Image.open(path) as image:
                image.load()

                image = (
                    ImageOps.exif_transpose(
                        image
                    )
                )

                width, height = (
                    image.size
                )

                crop = image.crop(
                    (
                        0,
                        int(height * 0.68),
                        width,
                        height,
                    )
                )

                crop.save(
                    crop_path,
                    format="PNG",
                )

            candidates = []

            for psm in (
                3,
                6,
                11,
            ):
                result = _run_tesseract(
                    crop_path,
                    psm=psm,
                )

                if not result["ok"]:
                    continue

                text = (
                    result.get("text")
                    or ""
                )

                totals = (
                    _find_footer_totals(
                        text
                    )
                )

                quality = (
                    _footer_quality(
                        totals
                    )
                )

                candidates.append({
                    **result,
                    "totals": totals,
                    "quality": quality,
                })

            if not candidates:
                return {
                    "ok": False,
                    "text": "",
                    "method": "",
                    "totals": {
                        "base": "",
                        "iva": "",
                        "total": "",
                    },
                }

            candidates.sort(
                key=lambda item: (
                    item["quality"],
                    len(item["text"]),
                ),
                reverse=True,
            )

            best = candidates[0]

            return {
                "ok": (
                    best["quality"] > 0
                ),
                "text": best["text"],
                "method": (
                    "image_footer_"
                    f"psm{best['psm']}"
                ),
                "totals": (
                    best["totals"]
                ),
                "selected_psm": (
                    best["psm"]
                ),
            }

    except Exception:
        return {
            "ok": False,
            "text": "",
            "method": "",
            "totals": {
                "base": "",
                "iva": "",
                "total": "",
            },
        }


def extract_basic_budget(
    *,
    path,
    extension,
    providers,
):
    extension = (
        extension or ""
    ).lower()

    footer_result = None

    if extension == ".pdf":
        from apps.gestion.services.pdf_extractor import (
            extract_pdf_text,
        )

        text_result = extract_pdf_text(
            path,
            max_pages=10,
        )

    elif extension in IMAGE_EXTENSIONS:
        text_result = (
            _extract_image_text(
                path
            )
        )

    else:
        text_result = {
            "ok": False,
            "text": "",
            "method": "",
            "ocr_used": False,
            "error": (
                "Formato no soportado "
                "por el lector básico."
            ),
        }

    text = (
        text_result.get("text")
        or ""
    )

    analysis = (
        analizar_texto_presupuesto(
            text,
            providers,
        )
    )

    detected = (
        analysis.get("detected")
        or {}
    )

    # Fallback económico exclusivamente
    # para imagen, y solo cuando la lectura
    # completa no obtuvo los totales.
    if (
        extension in IMAGE_EXTENSIONS
        and (
            not detected.get(
                "base_imponible"
            )
            or not detected.get(
                "iva"
            )
            or not detected.get(
                "total"
            )
        )
    ):
        footer_result = (
            _extract_image_footer_text(
                path
            )
        )

        footer_totals = (
            footer_result.get(
                "totals"
            )
            or {}
        )

        if (
            not detected.get(
                "base_imponible"
            )
            and footer_totals.get(
                "base"
            )
        ):
            detected[
                "base_imponible"
            ] = footer_totals["base"]

        if (
            not detected.get("iva")
            and footer_totals.get(
                "iva"
            )
        ):
            detected["iva"] = (
                footer_totals["iva"]
            )

        if (
            not detected.get("total")
            and footer_totals.get(
                "total"
            )
        ):
            detected["total"] = (
                footer_totals["total"]
            )

    analysis["detected"] = detected

    result = {
        "ok": bool(
            text_result.get("ok")
        ),
        "method": (
            text_result.get("method")
            or ""
        ),
        "ocr_used": bool(
            text_result.get(
                "ocr_used"
            )
        ),
        "error": (
            text_result.get("error")
            or ""
        ),
        "text": text,
        "text_len": len(text),
        **analysis,
    }

    if (
        text_result.get(
            "selected_psm"
        )
        is not None
    ):
        result["selected_psm"] = (
            text_result[
                "selected_psm"
            ]
        )

    if text_result.get(
        "candidates"
    ):
        result[
            "ocr_candidates"
        ] = text_result[
            "candidates"
        ]

    if footer_result:
        result[
            "footer_ocr"
        ] = {
            "ok": footer_result.get(
                "ok",
                False,
            ),
            "method": (
                footer_result.get(
                    "method"
                )
                or ""
            ),
            "selected_psm": (
                footer_result.get(
                    "selected_psm"
                )
            ),
            "totals": (
                footer_result.get(
                    "totals"
                )
                or {}
            ),
        }

    return result

def _stage_dir():
    path = (
        Path(settings.MEDIA_ROOT)
        / "comparativas"
        / "_imports"
    )

    path.mkdir(
        parents=True,
        exist_ok=True,
    )

    return path


def _cleanup_old_staged():
    now = time.time()

    for path in _stage_dir().iterdir():
        try:
            age = (
                now
                - path.stat().st_mtime
            )

            if age > 86400:
                path.unlink(
                    missing_ok=True
                )
        except OSError:
            continue


def stage_presupuesto(
    *,
    uploaded_file,
    user_id,
    comparativa_uuid,
):
    _cleanup_old_staged()

    extension = Path(
        uploaded_file.name or ""
    ).suffix.lower()

    random_name = (
        f"{uuid.uuid4().hex}"
        f"{extension}"
    )

    path = (
        _stage_dir()
        / random_name
    )

    digest = hashlib.sha256()

    with path.open("wb") as handle:
        for chunk in (
            uploaded_file.chunks()
        ):
            digest.update(chunk)
            handle.write(chunk)

    payload = {
        "file": random_name,
        "original_name": Path(
            uploaded_file.name
            or "presupuesto"
        ).name,
        "content_type": (
            getattr(
                uploaded_file,
                "content_type",
                "",
            )
            or ""
        ),
        "extension": extension,
        "sha256": (
            digest.hexdigest()
        ),
        "user_id": str(user_id),
        "comparativa_uuid": str(
            comparativa_uuid
        ),
    }

    token = signing.dumps(
        payload,
        salt=STAGE_SALT,
        compress=True,
    )

    return {
        **payload,
        "token": token,
        "path": path,
        "analysis_path": (
            path.with_suffix(
                path.suffix + ".json"
            )
        ),
    }


def save_staged_analysis(
    staged,
    analysis,
):
    staged["analysis_path"].write_text(
        json.dumps(
            analysis,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )


def resolve_staged_presupuesto(
    *,
    token,
    user_id,
    comparativa_uuid,
):
    payload = signing.loads(
        token,
        salt=STAGE_SALT,
        max_age=STAGE_MAX_AGE,
    )

    if (
        str(payload.get("user_id"))
        != str(user_id)
    ):
        raise signing.BadSignature(
            "Usuario no coincide."
        )

    if (
        str(
            payload.get(
                "comparativa_uuid"
            )
        )
        != str(comparativa_uuid)
    ):
        raise signing.BadSignature(
            "Comparativa no coincide."
        )

    filename = payload.get(
        "file"
    )

    if (
        not filename
        or Path(filename).name
        != filename
    ):
        raise signing.BadSignature(
            "Nombre temporal inválido."
        )

    path = (
        _stage_dir()
        / filename
    )

    if not path.exists():
        raise FileNotFoundError(
            "El archivo temporal "
            "ya no está disponible."
        )

    digest = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()

    if (
        digest
        != payload.get("sha256")
    ):
        raise signing.BadSignature(
            "El archivo temporal "
            "ha cambiado."
        )

    analysis_path = (
        path.with_suffix(
            path.suffix + ".json"
        )
    )

    analysis = {}

    if analysis_path.exists():
        analysis = json.loads(
            analysis_path.read_text(
                encoding="utf-8"
            )
        )

    return {
        **payload,
        "token": token,
        "path": path,
        "analysis_path": (
            analysis_path
        ),
        "analysis": analysis,
    }


def delete_staged_presupuesto(
    staged,
):
    for key in (
        "path",
        "analysis_path",
    ):
        path = staged.get(key)

        if not path:
            continue

        try:
            Path(path).unlink(
                missing_ok=True
            )
        except OSError:
            pass


def _same_candidate(
    ofertante,
    *,
    name,
    nif,
):
    nif_norm = _norm_tax(nif)

    if (
        nif_norm
        and _norm_tax(
            ofertante.nif
        ) == nif_norm
    ):
        return True

    return (
        _norm(ofertante.nombre)
        == _norm(name)
        and bool(_norm(name))
    )


@transaction.atomic
def create_from_staged_budget(
    *,
    comparativa,
    provider,
    cleaned_data,
    staged,
    analysis,
    user,
    v3_ingestion=False,
):
    locked = (
        Comparativa.objects
        .select_for_update()
        .get(pk=comparativa.pk)
    )

    if provider:
        ofertante = (
            locked.ofertantes
            .filter(
                tipo=(
                    Ofertante.Tipo
                    .PROVEEDOR
                ),
                proveedor_ref_id=(
                    provider["id"]
                ),
            )
            .first()
        )

        if ofertante is None:
            ofertante = (
                Ofertante.objects
                .create(
                    comparativa=locked,
                    tipo=(
                        Ofertante.Tipo
                        .PROVEEDOR
                    ),
                    proveedor_ref_id=(
                        provider["id"]
                    ),
                    nombre=(
                        provider["nombre"]
                    ),
                    nif=(
                        provider["nif"]
                    ),
                    email=(
                        provider["email"]
                    ),
                    telefono=(
                        provider["telefono"]
                    ),
                )
            )
    else:
        name = (
            cleaned_data.get("nombre")
            or ""
        ).strip()

        nif = (
            cleaned_data.get("nif")
            or ""
        ).strip()

        ofertante = None

        for current in (
            locked.ofertantes
            .filter(
                tipo=(
                    Ofertante.Tipo
                    .CANDIDATO
                )
            )
        ):
            if _same_candidate(
                current,
                name=name,
                nif=nif,
            ):
                ofertante = current
                break

        if ofertante is None:
            ofertante = (
                Ofertante.objects
                .create(
                    comparativa=locked,
                    tipo=(
                        Ofertante.Tipo
                        .CANDIDATO
                    ),
                    nombre=name,
                    nif=nif,
                )
            )

    # En el camino V3 el staging nunca es autoridad semántica: la oferta se
    # crea vacía y solo la confirmación humana de la preview V3 la completa.
    offer_data = {
        "fecha_documento": cleaned_data.get("fecha_documento"),
        "referencia": cleaned_data.get("referencia") or "",
        "base": cleaned_data.get("base"),
        "impuestos": cleaned_data.get("impuestos"),
        "total": cleaned_data.get("total"),
        "observaciones": cleaned_data.get("observaciones") or "",
    }
    # Los valores introducidos explícitamente en el formulario siguen siendo
    # una confirmación humana de compatibilidad; el documento queda además
    # marcado para revisión V3 y no se toma ningún dato heurístico automático.

    oferta = crear_oferta(
        ofertante=ofertante,
        cleaned_data=offer_data,
        user=user,
    )

    with staged["path"].open(
        "rb"
    ) as handle:
        django_file = File(
            handle,
            name=(
                staged[
                    "original_name"
                ]
            ),
        )

        django_file.content_type = (
            staged.get(
                "content_type"
            )
            or ""
        )

        documento, _ = (
            guardar_documento(
                oferta=oferta,
                uploaded_file=(
                    django_file
                ),
                user=user,
            )
        )

    document_data = {
        key: value
        for key, value in analysis.items()
        if key != "text"
    }

    documento.texto_extraido = (
        analysis.get("text")
        or ""
    )

    documento.datos_extraidos = {
        "importacion_basica_presupuesto": (
            {
                **document_data,
                "semantic_authority": (
                    "document_intelligence_v3"
                    if v3_ingestion
                    else "legacy_import"
                ),
            }
        )
    }

    documento.save(
        update_fields=(
            "texto_extraido",
            "datos_extraidos",
        )
    )

    return (
        ofertante,
        oferta,
        documento,
    )
