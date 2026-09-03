import mimetypes
from collections.abc import Mapping
from pathlib import PurePosixPath

from django.db import DatabaseError, transaction

from .models import Archivo


class CloudReferenceError(RuntimeError):
    """La subida remota existe, pero su referencia local no es válida."""


def upsert_cloud_uploaded_reference(
    *,
    folder,
    item,
    actor,
    team,
):
    if not isinstance(item, Mapping):
        raise CloudReferenceError(
            "Nextcloud no devolvió datos documentales válidos."
        )

    storage_key = str(
        item.get("storage_key") or ""
    ).strip("/")

    remote_file_id = str(
        item.get("file_id") or ""
    ).strip()

    if not storage_key:
        raise CloudReferenceError(
            "La subida no devolvió una ruta documental."
        )

    if not remote_file_id:
        raise CloudReferenceError(
            "La subida no devolvió un identificador remoto."
        )

    filename = PurePosixPath(storage_key).name

    content_type = (
        str(item.get("content_type") or "").strip()
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )

    try:
        with transaction.atomic():
            # P2B3_CLOUD_REFERENCE_VERSION_ALLOCATION
            #
            # Todas las referencias Nextcloud comparten una
            # carpeta técnica. Dos rutas remotas distintas
            # pueden contener archivos con el mismo nombre.
            # Bloqueamos la carpeta para serializar la
            # asignación de versiones y evitar carreras.
            locked_folder = (
                folder.__class__
                .objects
                .select_for_update()
                .get(pk=folder.pk)
            )

            def next_available_version():
                latest_version = (
                    Archivo.objects
                    .select_for_update()
                    .filter(
                        carpeta=locked_folder,
                        nombre_logico=filename,
                    )
                    .order_by("-version")
                    .values_list(
                        "version",
                        flat=True,
                    )
                    .first()
                )

                return (
                    int(latest_version or 0)
                    + 1
                )

            matches = (
                Archivo.objects
                .select_for_update()
                .filter(
                    storage_provider="nextcloud",
                    storage_object_id=remote_file_id,
                )
                .order_by("pk")
            )

            if matches.count() > 1:
                raise CloudReferenceError(
                    "Existen referencias locales duplicadas "
                    "para el documento remoto."
                )

            archivo = matches.first()
            created = archivo is None

            if created:
                archivo = Archivo.objects.create(
                    carpeta=locked_folder,
                    team=team,
                    fichero="",
                    nombre_original=filename,
                    nombre_logico=filename,
                    descripcion="",
                    subido_por=actor,
                    tamano_bytes=int(
                        item.get("size") or 0
                    ),
                    version=next_available_version(),
                    storage_provider="nextcloud",
                    storage_key=storage_key,
                    storage_object_id=remote_file_id,
                    storage_version=str(
                        item.get("etag") or ""
                    ),
                    mime_type=content_type,
                )

                return archivo, True

            if (
                archivo.team_id
                and archivo.team_id != team.id
            ):
                raise CloudReferenceError(
                    "La referencia remota ya pertenece "
                    "a otra empresa."
                )

            target_version = int(
                archivo.version or 1
            )

            version_collision = (
                Archivo.objects
                .select_for_update()
                .filter(
                    carpeta=locked_folder,
                    nombre_logico=filename,
                    version=target_version,
                )
                .exclude(pk=archivo.pk)
                .exists()
            )

            if version_collision:
                target_version = (
                    next_available_version()
                )

            archivo.carpeta = locked_folder
            archivo.fichero = ""
            archivo.nombre_original = filename
            archivo.nombre_logico = filename
            archivo.tamano_bytes = int(
                item.get("size") or 0
            )
            archivo.storage_key = storage_key
            archivo.storage_version = str(
                item.get("etag") or ""
            )
            archivo.mime_type = content_type
            archivo.version = target_version

            if archivo.team_id is None:
                archivo.team = team

            if archivo.subido_por_id is None:
                archivo.subido_por = actor

            archivo.save(
                update_fields=[
                    "carpeta",
                    "team",
                    "fichero",
                    "nombre_original",
                    "nombre_logico",
                    "tamano_bytes",
                    "storage_key",
                    "storage_version",
                    "mime_type",
                    "version",
                    "subido_por",
                ]
            )

            return archivo, False

    except CloudReferenceError:
        raise

    except DatabaseError as exc:
        raise CloudReferenceError(
            "No se pudo guardar la referencia local "
            "del documento."
        ) from exc
