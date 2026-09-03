from pathlib import PurePosixPath

from django import template


register = template.Library()


VIDEO_EXTENSIONS = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".ogv",
    ".webm",
}


@register.filter
def es_video(archivo) -> bool:
    mime_type = str(
        getattr(archivo, "mime_type", "")
        or ""
    ).strip().lower()

    if mime_type.startswith("video/"):
        return True

    name = str(
        getattr(archivo, "nombre_original", "")
        or getattr(archivo, "storage_key", "")
        or ""
    )

    extension = PurePosixPath(
        name
    ).suffix.lower()

    return extension in VIDEO_EXTENSIONS
