# ============================================================================
# RRHH_CV_OCR_V1
# Lectura conservadora de currículos PDF. No persiste datos ni documentos.
# ============================================================================

import re
import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.gestion.services.pdf_extractor import extract_pdf_text


EMAIL_RE = re.compile(
    r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
    re.IGNORECASE,
)
LINKEDIN_RE = re.compile(
    r"(?:(?:https?://)?(?:www\.)?)linkedin\.com/in/[A-Z0-9_%./?=&+-]+",
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s().-]{7,}\d)(?!\w)")

SECTION_HEADINGS = {
    "EXPERIENCIA",
    "EXPERIENCIA PROFESIONAL",
    "FORMACION",
    "FORMACION ACADEMICA",
    "EDUCACION",
    "ESTUDIOS",
    "IDIOMAS",
    "HABILIDADES",
    "COMPETENCIAS",
    "CONTACTO",
    "DATOS PERSONALES",
    "OTROS DATOS",
    "REFERENCIAS",
    "CURRICULUM",
    "CURRICULUM VITAE",
    "CV",
}

NAME_EXCLUSIONS = SECTION_HEADINGS | {
    "PERFIL",
    "PERFIL PROFESIONAL",
    "RESUMEN",
    "RESUMEN PROFESIONAL",
    "SOBRE MI",
    "OBJETIVO PROFESIONAL",
    "DATOS DE CONTACTO",
}

PROFILE_LABELS = (
    "PERFIL PROFESIONAL",
    "RESUMEN PROFESIONAL",
    "SOBRE MI",
    "OBJETIVO PROFESIONAL",
    "PERFIL",
    "RESUMEN",
)

PROFESSION_TOKENS = (
    "ARQUITECT",
    "APAREJADOR",
    "INGENIER",
    "TECNIC",
    "ADMINISTR",
    "AUXILIAR",
    "ENFERMER",
    "COMERCIAL",
    "CONTABLE",
    "ABOGAD",
    "OPERARI",
    "RESPONSABLE",
    "JEFE",
    "PROJECT MANAGER",
    "DESARROLLADOR",
    "DEVELOPER",
    "DISEÑ",
    "CONSULTOR",
    "COORDINADOR",
)


def _strip_accents(value):
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(character)
    )


def _norm(value):
    return re.sub(r"\s+", " ", _strip_accents(value).upper()).strip()


def _clean_line(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t|•·")


def _lines(text):
    return [
        cleaned
        for cleaned in (_clean_line(line) for line in (text or "").splitlines())
        if cleaned
    ]


def _filename_name(filename):
    stem = Path(filename or "").stem
    # RRHH_CV_OCR_V1_1 · los guiones y guiones bajos separan palabras.
    # Se normalizan antes de retirar prefijos como CV o CURRICULUM.
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(
        r"(?i)\b(curriculum|curriculo|currículum|vitae|cv|resume)\b",
        " ",
        stem,
    )
    stem = re.sub(r"\b\d{4,}\b", " ", stem)
    stem = _clean_line(stem)
    words = stem.split()
    if 2 <= len(words) <= 6 and not any(char.isdigit() for char in stem):
        return " ".join(word.capitalize() for word in words)
    return ""


def _extract_email(text):
    match = EMAIL_RE.search(text or "")
    return match.group(1).strip(".,;:") if match else ""


def _normalize_phone(value):
    raw = _clean_line(value)
    digits = re.sub(r"\D", "", raw)
    if not 9 <= len(digits) <= 15:
        return ""
    if raw.startswith("+"):
        return "+" + digits
    if len(digits) == 11 and digits.startswith("34"):
        return "+" + digits
    if len(digits) == 9:
        return " ".join((digits[:3], digits[3:6], digits[6:]))
    return digits


def _extract_phone(text):
    candidates = []
    for match in PHONE_RE.finditer(text or ""):
        raw = match.group(1)
        if "/" in raw:
            continue
        normalized = _normalize_phone(raw)
        if not normalized:
            continue
        digits = re.sub(r"\D", "", normalized)
        priority = 0
        if normalized.startswith("+34"):
            priority += 4
        if len(digits) == 9 and digits[0] in "6789":
            priority += 3
        if raw.strip().startswith("+"):
            priority += 1
        candidates.append((priority, match.start(), normalized))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def _extract_linkedin(text):
    match = LINKEDIN_RE.search(text or "")
    if not match:
        return ""
    value = match.group(0).rstrip(".,;:)")
    if not value.lower().startswith(("http://", "https://")):
        value = "https://" + value
    return value


def _looks_like_name(line):
    clean = _clean_line(line)
    normalized = _norm(clean)
    if normalized in NAME_EXCLUSIONS:
        return False
    if len(clean) < 5 or len(clean) > 80:
        return False
    if any(token in clean.lower() for token in ("@", "http", "www.", "linkedin")):
        return False
    if any(character.isdigit() for character in clean):
        return False
    if ":" in clean or ";" in clean:
        return False
    words = clean.split()
    if not 2 <= len(words) <= 6:
        return False
    letter_words = [
        re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ'-]", "", word)
        for word in words
    ]
    if any(len(word) < 2 for word in letter_words):
        return False
    if any(token in normalized for token in PROFESSION_TOKENS):
        return False
    return True


def _extract_name(text, filename=""):
    lines = _lines(text)
    label_pattern = re.compile(
        r"(?i)^(?:nombre(?:\s+y\s+apellidos)?|candidato)\s*[:\-]\s*(.+)$"
    )
    for line in lines[:40]:
        match = label_pattern.match(line)
        if match and _looks_like_name(match.group(1)):
            return _clean_line(match.group(1))

    for line in lines[:25]:
        if _looks_like_name(line):
            return line

    return _filename_name(filename)


def _extract_city(text):
    lines = _lines(text)
    label_pattern = re.compile(
        r"(?i)^(?:ciudad|localidad|residencia|domicilio|poblaci[oó]n)"
        r"\s*[:\-]\s*(.{2,80})$"
    )
    for line in lines:
        match = label_pattern.match(line)
        if match:
            value = _clean_line(match.group(1)).split("|", 1)[0]
            return value[:120]

    postal_pattern = re.compile(
        r"\b\d{5}\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ .'-]{1,60})"
    )
    for line in lines:
        match = postal_pattern.search(line)
        if match:
            value = _clean_line(match.group(1))
            value = re.split(r"[,|]", value, maxsplit=1)[0].strip()
            return value[:120]

    return ""


def _is_heading(line):
    normalized = _norm(line).strip(":")
    return normalized in SECTION_HEADINGS or (
        len(normalized) <= 45
        and normalized
        and normalized == normalized.upper()
        and normalized in NAME_EXCLUSIONS
    )


def _extract_profile(text, name=""):
    lines = _lines(text)

    for index, line in enumerate(lines):
        normalized = _norm(line)
        for label in PROFILE_LABELS:
            if normalized == label:
                chunks = []
                for candidate in lines[index + 1:index + 5]:
                    if _is_heading(candidate):
                        break
                    if EMAIL_RE.search(candidate) or PHONE_RE.search(candidate):
                        continue
                    chunks.append(candidate)
                    if len(" ".join(chunks)) >= 160:
                        break
                value = _clean_line(" ".join(chunks))
                if value:
                    return value[:220]

            prefix = label + ":"
            if normalized.startswith(prefix):
                value = _clean_line(line.split(":", 1)[1])
                if value:
                    return value[:220]

    name_norm = _norm(name)
    for line in lines[:35]:
        normalized = _norm(line)
        if normalized == name_norm:
            continue
        if any(token in normalized for token in PROFESSION_TOKENS):
            if not EMAIL_RE.search(line) and not PHONE_RE.search(line):
                return _clean_line(line)[:220]

    return ""


def extract_cv_fields(text, filename=""):
    text = text or ""
    name = _extract_name(text, filename)
    payload = {
        "nombre_completo": name,
        "telefono": _extract_phone(text),
        "email": _extract_email(text),
        "ciudad": _extract_city(text),
        "perfil_profesional": _extract_profile(text, name),
        "linkedin_url": _extract_linkedin(text),
        "observaciones_candidato": "",
        "observaciones_revision": "",
    }
    missing = [
        label
        for field, label in (
            ("nombre_completo", "nombre"),
            ("telefono", "teléfono"),
            ("email", "correo"),
        )
        if not payload[field]
    ]
    return {
        "fields": payload,
        "missing": missing,
        "text_preview": text[:12000],
        "text_length": len(text),
    }


def analyze_cv_pdf(path, original_name=""):
    result = extract_pdf_text(path, max_pages=6)
    if not result.get("ok"):
        raise ValidationError(
            result.get("error") or "No se pudo leer el currículo PDF."
        )

    text = result.get("text") or ""
    if not text.strip():
        raise ValidationError(
            "No se detectó texto en el currículo. Revisa que el PDF sea legible."
        )

    parsed = extract_cv_fields(text, original_name)
    parsed.update(
        {
            "method": result.get("method") or "",
            "ocr_used": bool(result.get("ocr_used")),
            "pages": result.get("pages") or 0,
            "error": result.get("error") or "",
        }
    )
    return parsed


def pending_directory():
    configured = getattr(settings, "RRHH_CV_PENDING_DIR", "")
    path = Path(configured or "/tmp/portal_intasa_rrhh_cv_pending")
    path.mkdir(parents=True, exist_ok=True)
    return path
