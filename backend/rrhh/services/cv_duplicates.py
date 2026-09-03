# ============================================================================
# RRHH_CV_FAST_LOAD_DUPLICATE_DELETE_V1
# ============================================================================

import hashlib
import re
import unicodedata
from pathlib import Path


def normalize_text(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(
        char
        for char in value
        if not unicodedata.combining(char)
    )
    value = value.casefold().strip()
    return re.sub(r"\s+", " ", value)


def normalize_email(value):
    return normalize_text(value).replace(" ", "")


def normalize_phone(value):
    digits = re.sub(r"\D+", "", str(value or ""))
    if len(digits) > 9 and digits.startswith("34"):
        digits = digits[-9:]
    return digits


def normalize_filename(value):
    name = Path(str(value or "")).name
    stem = Path(name).stem
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return normalize_text(stem)


def sha256_stream(stream):
    digest = hashlib.sha256()
    original_position = None

    try:
        original_position = stream.tell()
    except (AttributeError, OSError):
        original_position = None

    try:
        stream.seek(0)
    except (AttributeError, OSError):
        pass

    if hasattr(stream, "chunks"):
        iterator = stream.chunks()
    else:
        iterator = iter(lambda: stream.read(1024 * 1024), b"")

    for chunk in iterator:
        if chunk:
            digest.update(chunk)

    try:
        stream.seek(
            original_position
            if original_position is not None
            else 0
        )
    except (AttributeError, OSError):
        pass

    return digest.hexdigest()


def sha256_uploaded_file(uploaded):
    return sha256_stream(uploaded)


def sha256_path(path):
    with Path(path).open("rb") as handle:
        return sha256_stream(handle)


def sha256_file_field(file_field):
    if not file_field:
        return ""

    try:
        file_field.open("rb")
        return sha256_stream(file_field)
    except (FileNotFoundError, OSError, ValueError):
        return ""
    finally:
        try:
            file_field.close()
        except Exception:
            pass


def find_duplicate_applications(
    process,
    *,
    cv_sha256="",
    email="",
    phone="",
    name="",
    filename="",
    exclude_pk=None,
):
    from rrhh.models import Candidatura

    wanted_email = normalize_email(email)
    wanted_phone = normalize_phone(phone)
    wanted_name = normalize_text(name)
    wanted_filename = normalize_filename(filename)
    wanted_hash = str(cv_sha256 or "").strip().lower()

    queryset = (
        Candidatura.objects
        .filter(proceso=process)
        .select_related("candidato", "proceso")
        .order_by("-fecha_solicitud", "-id")
    )

    if exclude_pk:
        queryset = queryset.exclude(pk=exclude_pk)

    matches = []

    for application in queryset:
        strong_reasons = []
        warning_reasons = []

        if (
            wanted_hash
            and application.cv_sha256
            and application.cv_sha256.lower() == wanted_hash
        ):
            strong_reasons.append("PDF idéntico")

        existing_email = normalize_email(
            application.candidato.email
        )
        if (
            wanted_email
            and existing_email
            and existing_email == wanted_email
        ):
            strong_reasons.append("mismo correo")

        existing_phone = normalize_phone(
            application.candidato.telefono
        )
        if (
            len(wanted_phone) >= 7
            and len(existing_phone) >= 7
            and existing_phone == wanted_phone
        ):
            strong_reasons.append("mismo teléfono")

        existing_name = normalize_text(
            application.candidato.nombre_completo
        )
        if (
            wanted_name
            and existing_name
            and existing_name == wanted_name
        ):
            warning_reasons.append("mismo nombre")

        existing_filename = normalize_filename(
            application.cv_nombre
        )
        if (
            wanted_filename
            and existing_filename
            and existing_filename == wanted_filename
        ):
            warning_reasons.append("mismo nombre de PDF")

        if strong_reasons or warning_reasons:
            matches.append(
                {
                    "candidatura": application,
                    "strong": bool(strong_reasons),
                    "hard": "PDF idéntico" in strong_reasons,
                    "strong_reasons": strong_reasons,
                    "warning_reasons": warning_reasons,
                }
            )

    return matches


def resolve_candidate_for_team(
    team,
    *,
    email="",
    phone="",
):
    from rrhh.models import Candidato

    wanted_email = normalize_email(email)
    wanted_phone = normalize_phone(phone)

    if not wanted_email and len(wanted_phone) < 7:
        return None

    email_matches = []
    phone_matches = []

    for candidate in (
        Candidato.objects
        .filter(team=team)
        .order_by("id")
    ):
        if (
            wanted_email
            and normalize_email(candidate.email) == wanted_email
        ):
            email_matches.append(candidate)

        if (
            len(wanted_phone) >= 7
            and normalize_phone(candidate.telefono) == wanted_phone
        ):
            phone_matches.append(candidate)

    if email_matches and phone_matches:
        phone_ids = {item.pk for item in phone_matches}
        intersection = [
            item
            for item in email_matches
            if item.pk in phone_ids
        ]
        if len(intersection) == 1:
            return intersection[0]
        return None

    if len(email_matches) == 1:
        return email_matches[0]

    if len(phone_matches) == 1:
        return phone_matches[0]

    return None


def delete_stored_file(storage, name):
    if not storage or not name:
        return
    try:
        storage.delete(name)
    except Exception:
        # La referencia de base de datos ya se ha limpiado. Un fallo del
        # proveedor no debe romper la transacción confirmada.
        return
