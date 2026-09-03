from __future__ import annotations

import hashlib
from collections.abc import Iterable

from actividad.models import ActividadPlataforma
from actividad.services import registrar_actividad


MAX_METADATA_ITEMS = 100


def ruta_carpeta_local(carpeta) -> str:
    """
    Construye una ruta legible sin depender del almacenamiento físico.
    """
    parts = []
    node = carpeta
    visited = set()

    while node is not None:
        node_id = getattr(node, "pk", None)

        if node_id in visited:
            break

        if node_id is not None:
            visited.add(node_id)

        nombre = str(
            getattr(node, "nombre", "") or ""
        ).strip()

        if nombre:
            parts.append(nombre)

        node = getattr(node, "parent", None)

    parts.reverse()

    return "/".join(parts) or "Archivos"


def _nombre_archivo(archivo) -> str:
    return (
        str(
            getattr(
                archivo,
                "nombre_original",
                "",
            )
            or getattr(
                archivo,
                "nombre_logico",
                "",
            )
            or archivo
        )
        .strip()
    )


def _clave_idempotencia(
    *,
    actor_id,
    team_id,
    storage_provider,
    destino,
    archivo_ids,
) -> str:
    raw = "|".join(
        [
            str(actor_id or ""),
            str(team_id or ""),
            str(storage_provider or ""),
            str(destino or ""),
            ",".join(
                str(value)
                for value in archivo_ids
            ),
        ]
    )

    digest = hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()

    return f"archivos:subida:{digest}"


def registrar_subida_documental(
    *,
    actor,
    team,
    archivos: Iterable,
    destino,
    url,
    storage_provider,
    carpetas_creadas=0,
    operation_id=None,
    policy="",
    audit_metadata=None,
    diferir_hasta_commit=True,
):
    """
    Crea una única actividad funcional por operación de subida.

    Los archivos deben haber sido guardados e indexados previamente.
    """
    archivos = [
        archivo
        for archivo in archivos
        if getattr(archivo, "pk", None)
    ]

    if not archivos:
        return None

    archivos = sorted(
        archivos,
        key=lambda archivo: archivo.pk,
    )

    archivo_ids = [
        archivo.pk
        for archivo in archivos
    ]

    nombres = [
        _nombre_archivo(archivo)
        for archivo in archivos
    ]

    cantidad = len(archivos)
    destino = str(destino or "Archivos").strip()
    storage_provider = str(
        storage_provider or "local"
    ).strip()

    if cantidad == 1:
        objeto = archivos[0]
        objeto_repr = nombres[0]

        descripcion = (
            f'ha subido «{nombres[0]}» '
            f"a {destino}."
        )

        tipo_objeto = ""
        objeto_id = None
    else:
        objeto = None
        objeto_repr = f"{cantidad} archivos"

        descripcion = (
            f"ha subido {cantidad} archivos "
            f"a {destino}."
        )

        tipo_objeto = (
            "archivos.subida_documental"
        )

        objeto_id = archivo_ids[0]

    metadata_ids = archivo_ids[
        :MAX_METADATA_ITEMS
    ]

    metadata_names = nombres[
        :MAX_METADATA_ITEMS
    ]

    metadata = {
        "cantidad": cantidad,
        "archivo_ids": metadata_ids,
        "nombres": metadata_names,
        "destino": destino,
        "storage_provider": storage_provider,
        "carpetas_creadas": int(
            carpetas_creadas or 0
        ),
        "metadata_truncada": (
            cantidad > MAX_METADATA_ITEMS
        ),
    }

    # P3_FOLDER_UPLOAD_AUDIT_METADATA
    operation_id = str(
        operation_id or ""
    ).strip()

    policy = str(
        policy or ""
    ).strip().lower()

    if operation_id:
        metadata["operation_id"] = (
            operation_id
        )

    if policy:
        metadata["collision_policy"] = (
            policy
        )

    if audit_metadata:
        metadata.update(
            dict(audit_metadata)
        )

    return registrar_actividad(
        modulo="archivos",
        accion="subida",
        actor=actor,
        team=team,
        objeto=objeto,
        tipo_objeto=tipo_objeto,
        objeto_id=objeto_id,
        objeto_repr=objeto_repr,
        descripcion=descripcion,
        url=url,
        visibilidad=(
            ActividadPlataforma
            .Visibilidad
            .EQUIPO
        ),
        origen=(
            ActividadPlataforma
            .Origen
            .EXPLICITO
        ),
        metadata=metadata,
        agrupacion_key=(
            "archivos:subida:"
            f"{getattr(team, 'pk', '')}:"
            f"{getattr(actor, 'pk', '')}"
        ),
        clave_idempotencia=(
            _clave_idempotencia(
                actor_id=getattr(
                    actor,
                    "pk",
                    None,
                ),
                team_id=getattr(
                    team,
                    "pk",
                    None,
                ),
                storage_provider=(
                    storage_provider
                ),
                destino=destino,
                archivo_ids=archivo_ids,
            )
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )


# ARCHIVOS_MUTATION_ACTIVITY_V1
from uuid import uuid4


DOCUMENT_MUTATION_ACTIONS = {
    "crear_carpeta",
    "renombrar",
    "mover",
    "eliminar",
}


def _visibilidad_operacion_documental(team):
    if getattr(team, "pk", None):
        return (
            ActividadPlataforma
            .Visibilidad
            .EQUIPO
        )

    return (
        ActividadPlataforma
        .Visibilidad
        .ACTOR
    )


def registrar_operacion_documental(
    *,
    actor,
    team,
    accion,
    tipo_elemento,
    nombre="",
    nombre_anterior="",
    nombre_nuevo="",
    ruta_origen="",
    ruta_destino="",
    url="",
    storage_provider="local",
    objeto=None,
    tipo_objeto="",
    objeto_id=None,
    cantidad=1,
    nombres=None,
    metadata_extra=None,
    operation_id=None,
    diferir_hasta_commit=True,
):
    """
    Registra una operación funcional explícita.

    No se invoca desde señales, sincronizaciones,
    aperturas, descargas ni indexaciones automáticas.
    """
    accion = str(
        accion or ""
    ).strip().lower()

    if accion not in DOCUMENT_MUTATION_ACTIONS:
        raise ValueError(
            "Acción documental no válida."
        )

    tipo_elemento = str(
        tipo_elemento or ""
    ).strip().lower()

    valid_types = {
        "archivo",
        "carpeta",
        "archivos",
    }

    if tipo_elemento not in valid_types:
        raise ValueError(
            "Tipo de elemento documental no válido."
        )

    cantidad = max(
        int(cantidad or 1),
        1,
    )

    nombre = str(
        nombre or ""
    ).strip()

    nombre_anterior = str(
        nombre_anterior or ""
    ).strip()

    nombre_nuevo = str(
        nombre_nuevo or ""
    ).strip()

    ruta_origen = str(
        ruta_origen or ""
    ).strip()

    ruta_destino = str(
        ruta_destino or ""
    ).strip()

    storage_provider = str(
        storage_provider or "local"
    ).strip()

    names = [
        str(value or "").strip()
        for value in (nombres or [])
        if str(value or "").strip()
    ]

    display_name = (
        nombre_nuevo
        or nombre
        or nombre_anterior
    )

    singular_label = {
        "archivo": "archivo",
        "carpeta": "carpeta",
        "archivos": "archivo",
    }[tipo_elemento]

    article = {
        "archivo": "el",
        "carpeta": "la",
        "archivos": "los",
    }[tipo_elemento]

    metadata_extra = dict(
        metadata_extra or {}
    )

    if accion == "crear_carpeta":
        descripcion = (
            f'ha creado la carpeta '
            f'«{display_name}»'
        )

        if ruta_destino:
            descripcion += (
                f" en {ruta_destino}"
            )

        descripcion += "."

    elif accion == "renombrar":
        descripcion = (
            f"ha renombrado {article} "
            f"{singular_label} "
            f"«{nombre_anterior}» como "
            f"«{nombre_nuevo}»"
        )

        location = (
            ruta_destino
            or ruta_origen
        )

        if location:
            descripcion += (
                f" en {location}"
            )

        descripcion += "."

    elif accion == "mover":
        descripcion = (
            f"ha movido {article} "
            f"{singular_label} "
            f"«{display_name}»"
        )

        if ruta_origen:
            descripcion += (
                f" de {ruta_origen}"
            )

        if ruta_destino:
            descripcion += (
                f" a {ruta_destino}"
            )

        descripcion += "."

    else:
        if (
            tipo_elemento == "archivos"
            or cantidad > 1
        ):
            descripcion = (
                f"ha eliminado "
                f"{cantidad} archivos"
            )
        else:
            descripcion = (
                f"ha eliminado {article} "
                f"{singular_label} "
                f"«{display_name}»"
            )

        if (
            tipo_elemento == "carpeta"
            and (
                metadata_extra.get(
                    "subcarpetas_eliminadas",
                    0,
                )
                or metadata_extra.get(
                    "archivos_eliminados",
                    0,
                )
            )
        ):
            descripcion += (
                " y todo su contenido"
            )

        if ruta_origen:
            descripcion += (
                f" de {ruta_origen}"
            )

        descripcion += "."

    object_repr = (
        f"{cantidad} archivos"
        if (
            tipo_elemento == "archivos"
            or cantidad > 1
        )
        else display_name
    )

    operation_id = str(
        operation_id
        or uuid4().hex
    ).strip()

    metadata = {
        "tipo_elemento": tipo_elemento,
        "nombre": nombre,
        "nombre_anterior": nombre_anterior,
        "nombre_nuevo": nombre_nuevo,
        "ruta_origen": ruta_origen,
        "ruta_destino": ruta_destino,
        "cantidad": cantidad,
        "nombres": names[
            :MAX_METADATA_ITEMS
        ],
        "storage_provider": storage_provider,
        "metadata_truncada": (
            len(names) > MAX_METADATA_ITEMS
        ),
        "operation_id": operation_id,
    }

    metadata.update(metadata_extra)

    return registrar_actividad(
        modulo="archivos",
        accion=accion,
        actor=actor,
        team=team,
        objeto=objeto,
        tipo_objeto=(
            tipo_objeto
            if objeto is None
            else ""
        ),
        objeto_id=(
            objeto_id
            if objeto is None
            else None
        ),
        objeto_repr=object_repr,
        descripcion=descripcion,
        url=str(url or "").strip(),
        visibilidad=(
            _visibilidad_operacion_documental(
                team
            )
        ),
        origen=(
            ActividadPlataforma
            .Origen
            .EXPLICITO
        ),
        metadata=metadata,
        agrupacion_key=(
            f"archivos:{accion}:"
            f"{getattr(team, 'pk', '')}:"
            f"{getattr(actor, 'pk', '')}"
        ),
        clave_idempotencia=(
            f"archivos:operacion:"
            f"{accion}:{operation_id}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )

