import hashlib
import io
import re
import zipfile
from pathlib import Path, PurePosixPath

from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename
from PIL import Image, UnidentifiedImageError


MAX_FILES = 5
MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_TOTAL_SIZE = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
MAX_IMAGE_SIDE = 12_000
MAX_ZIP_ENTRIES = 1_000
MAX_ZIP_UNCOMPRESSED = 100 * 1024 * 1024
MAX_ZIP_RATIO = 100

ALLOWED_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".docx",
    ".xlsx", ".xls", ".csv", ".txt",
}
REJECTED_EXTENSIONS = {
    ".svg", ".svgz", ".html", ".htm", ".js", ".exe", ".com",
    ".bat", ".cmd", ".sh", ".ps1", ".zip", ".docm", ".xlsm",
    ".xlsb", ".jar", ".msi", ".dll", ".scr",
}
MIME_BY_EXTENSION = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg", "image/jpg"},
    ".jpeg": {"image/jpeg", "image/jpg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    },
    ".xls": {"application/vnd.ms-excel", "application/octet-stream"},
    ".csv": {"text/csv", "text/plain", "application/csv", "application/vnd.ms-excel"},
    ".txt": {"text/plain"},
}
DETECTED_MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".txt": "text/plain",
}


def safe_display_name(name):
    basename = str(name or "archivo").replace("\\", "/").rsplit("/", 1)[-1]
    basename = re.sub(r"[\x00-\x1f\x7f]+", "_", basename).strip(" .")
    return get_valid_filename(basename or "archivo")[:255]


def _rewind(upload):
    try:
        upload.seek(0)
    except Exception:
        pass


def _read_head(upload, size=65536):
    _rewind(upload)
    data = upload.read(size)
    _rewind(upload)
    return data


def _validate_name(upload):
    raw = str(getattr(upload, "name", "") or "")
    cleaned = raw.replace("\\", "/").rsplit("/", 1)[-1]
    suffixes = [item.lower() for item in Path(cleaned).suffixes]
    extension = suffixes[-1] if suffixes else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise ValidationError("Tipo de archivo no permitido.", code="extension")
    if len(suffixes) > 1 and any(
        suffix in ALLOWED_EXTENSIONS or suffix in REJECTED_EXTENSIONS
        for suffix in suffixes[:-1]
    ):
        raise ValidationError("El nombre contiene una extensión doble engañosa.", code="double_extension")
    return extension, safe_display_name(cleaned)


def _validate_declared_mime(upload, extension):
    declared = str(getattr(upload, "content_type", "") or "").split(";", 1)[0].strip().lower()
    if not declared or declared not in MIME_BY_EXTENSION[extension]:
        raise ValidationError("El tipo MIME declarado no coincide con el formato.", code="declared_mime")
    return declared


def _validate_image(upload, extension):
    _rewind(upload)
    try:
        with Image.open(upload) as image:
            image.verify()
        _rewind(upload)
        with Image.open(upload) as image:
            width, height = image.size
            actual = (image.format or "").upper()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("La imagen está vacía o corrupta.", code="image_invalid") from exc
    finally:
        _rewind(upload)
    expected = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}[extension]
    if actual != expected:
        raise ValidationError("La firma de imagen no coincide con la extensión.", code="image_signature")
    if width <= 0 or height <= 0 or width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE or width * height > MAX_IMAGE_PIXELS:
        raise ValidationError("La imagen supera las dimensiones seguras.", code="image_dimensions")


def _validate_ooxml(upload, extension):
    _rewind(upload)
    try:
        with zipfile.ZipFile(upload) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_ZIP_ENTRIES:
                raise ValidationError("El contenedor OOXML tiene demasiadas entradas.", code="zip_entries")
            total = 0
            names = set()
            for info in infos:
                posix = PurePosixPath(info.filename)
                if posix.is_absolute() or ".." in posix.parts:
                    raise ValidationError("El contenedor OOXML contiene rutas no seguras.", code="zip_path")
                total += info.file_size
                if total > MAX_ZIP_UNCOMPRESSED:
                    raise ValidationError("El contenedor OOXML se expande en exceso.", code="zip_size")
                if info.file_size and (not info.compress_size or info.file_size / info.compress_size > MAX_ZIP_RATIO):
                    raise ValidationError("El contenedor OOXML tiene una ratio de compresión insegura.", code="zip_ratio")
                lowered = info.filename.lower()
                names.add(lowered)
                if "vbaproject" in lowered or "/macros/" in lowered or lowered.endswith(".bin"):
                    raise ValidationError("No se admiten documentos con macros.", code="macros")
            required = "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
            if "[content_types].xml" not in names or required not in names:
                raise ValidationError("El contenedor OOXML no corresponde al formato declarado.", code="ooxml_structure")
            content_types = archive.read("[Content_Types].xml")[:262144].lower()
            if b"macroenabled" in content_types or b"vbaproject" in content_types:
                raise ValidationError("No se admiten documentos con macros.", code="macros")
    except zipfile.BadZipFile as exc:
        raise ValidationError("El documento OOXML está corrupto.", code="ooxml_invalid") from exc
    finally:
        _rewind(upload)


def _validate_xls(upload):
    signature = _read_head(upload, 8)
    if signature != bytes.fromhex("D0CF11E0A1B11AE1"):
        raise ValidationError("La firma XLS no es válida.", code="xls_signature")
    _rewind(upload)
    previous = b""
    for chunk in upload.chunks(65536):
        probe = (previous + chunk).lower()
        if b"_vba_project_cur" in probe or b"vbaproject" in probe or b"macros" in probe:
            _rewind(upload)
            raise ValidationError("No se admiten hojas con macros.", code="macros")
        previous = probe[-32:]
    _rewind(upload)


def _validate_text(upload):
    sample = _read_head(upload)
    if b"\x00" in sample:
        raise ValidationError("El archivo de texto contiene datos binarios.", code="text_binary")
    if sample:
        controls = sum(byte < 9 or 13 < byte < 32 for byte in sample)
        if controls / len(sample) > 0.01:
            raise ValidationError("El archivo de texto contiene datos binarios.", code="text_binary")
        try:
            sample.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                sample.decode("cp1252")
            except UnicodeDecodeError as exc:
                raise ValidationError("La codificación del texto no es válida.", code="text_encoding") from exc


def validate_attachment(upload):
    size = int(getattr(upload, "size", 0) or 0)
    if size <= 0:
        raise ValidationError("El archivo está vacío.", code="empty")
    if size > MAX_FILE_SIZE:
        raise ValidationError("El archivo supera 10 MB.", code="file_size")
    extension, display_name = _validate_name(upload)
    declared = _validate_declared_mime(upload, extension)
    if extension == ".pdf":
        if _read_head(upload, 5) != b"%PDF-":
            raise ValidationError("La firma PDF no es válida.", code="pdf_signature")
    elif extension in {".jpg", ".jpeg", ".png", ".webp"}:
        _validate_image(upload, extension)
    elif extension in {".docx", ".xlsx"}:
        _validate_ooxml(upload, extension)
    elif extension == ".xls":
        _validate_xls(upload)
    else:
        _validate_text(upload)
    digest = hashlib.sha256()
    _rewind(upload)
    for chunk in upload.chunks(1024 * 1024):
        digest.update(chunk)
    _rewind(upload)
    return {
        "original_name": str(getattr(upload, "name", "") or "")[:255],
        "safe_display_name": display_name,
        "declared_mime": declared,
        "detected_mime": DETECTED_MIME[extension],
        "extension": extension,
        "size_bytes": size,
        "sha256": digest.hexdigest(),
    }


def validate_attachment_batch(uploads):
    uploads = list(uploads or [])
    if len(uploads) > MAX_FILES:
        raise ValidationError("Solo se permiten 5 archivos por mensaje.", code="file_count")
    total = sum(int(getattr(upload, "size", 0) or 0) for upload in uploads)
    if total > MAX_TOTAL_SIZE:
        raise ValidationError("Los archivos superan 25 MB en total.", code="total_size")
    return [(upload, validate_attachment(upload)) for upload in uploads]
