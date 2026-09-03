from __future__ import annotations

from pathlib import PurePosixPath

from django.db.models import Q

from .activity import (
    registrar_operacion_documental,
)
from .models import Archivo
from .team_scope import (
    DocumentTeamResolutionError,
    resolve_document_team,
)


def _empty_snapshot(path=""):
    return {
        "path": str(path or "").strip("/"),
        "references": [],
        "reference_ids": [],
        "reference_names": [],
        "reference_count": 0,
        "assigned_team_ids": [],
        "unclassified_count": 0,
        "resolved_team": None,
    }


def snapshot_cloud_references(
    source_path,
):
    """
    Captura referencias locales antes de modificar
    la fuente de verdad remota.

    La ruta raíz vacía no representa una única empresa.
    """
    source = str(
        source_path or ""
    ).strip("/")

    if not source:
        return _empty_snapshot(source)

    references = list(
        Archivo.objects
        .filter(
            storage_provider="nextcloud"
        )
        .filter(
            Q(storage_key=source)
            | Q(
                storage_key__startswith=(
                    source + "/"
                )
            )
        )
        .select_related(
            "team",
            "subido_por",
        )
        .order_by("pk")
    )

    assigned_team_ids = sorted({
        reference.team_id
        for reference in references
        if reference.team_id
    })

    unclassified_count = sum(
        1
        for reference in references
        if reference.team_id is None
    )

    resolved_team = None

    if (
        len(assigned_team_ids) == 1
        and unclassified_count == 0
    ):
        resolved_team = next(
            reference.team
            for reference in references
            if reference.team_id
        )

    return {
        "path": source,
        "references": references,
        "reference_ids": [
            reference.pk
            for reference in references
        ],
        "reference_names": [
            (
                reference.nombre_original
                or reference.nombre_logico
                or str(reference)
            )
            for reference in references
        ],
        "reference_count": len(references),
        "assigned_team_ids": assigned_team_ids,
        "unclassified_count": (
            unclassified_count
        ),
        "resolved_team": resolved_team,
    }


def resolve_cloud_activity_team(
    request,
    *,
    snapshot=None,
    explicit_team=None,
):
    """
    Política conservadora:

    1. Team explícito, cuando la operación lo aporta.
    2. Todas las referencias clasificadas en un solo Team.
    3. Sin referencias: ámbito documental de la petición.
    4. Referencias mixtas o sin clasificar: actividad privada.
    """
    if explicit_team is not None:
        return (
            explicit_team,
            "explicit_team",
        )

    snapshot = snapshot or _empty_snapshot()

    reference_count = int(
        snapshot.get("reference_count")
        or 0
    )

    if reference_count:
        resolved_team = snapshot.get(
            "resolved_team"
        )

        if resolved_team is not None:
            return (
                resolved_team,
                "single_reference_team",
            )

        return (
            None,
            "mixed_or_unclassified_references",
        )

    try:
        team = resolve_document_team(
            request
        )

        return (
            team,
            "request_document_scope",
        )

    except DocumentTeamResolutionError:
        return (
            None,
            "private_unresolved_scope",
        )


def _parent_path(path):
    parent = str(
        PurePosixPath(
            str(path or "").strip("/")
        ).parent
    )

    return "" if parent == "." else parent


def registrar_operacion_cloud(
    *,
    request,
    accion,
    item,
    source="",
    destination="",
    snapshot=None,
    explicit_team=None,
    references_affected=0,
    url="",
    operation_id=None,
):
    """
    Traduce una operación remota exitosa a una
    actividad funcional de PORTAL INTASA.
    """
    source = str(
        source or ""
    ).strip("/")

    destination = str(
        destination or ""
    ).strip("/")

    snapshot = (
        snapshot
        if snapshot is not None
        else _empty_snapshot(source)
    )

    team, team_resolution = (
        resolve_cloud_activity_team(
            request,
            snapshot=snapshot,
            explicit_team=explicit_team,
        )
    )

    item = dict(item or {})

    is_folder = bool(
        item.get("is_folder")
    )

    tipo_elemento = (
        "carpeta"
        if is_folder
        else "archivo"
    )

    source_name = str(
        item.get("name")
        or (
            PurePosixPath(source).name
            if source
            else ""
        )
    ).strip()

    destination_name = (
        PurePosixPath(destination).name
        if destination
        else ""
    )

    source_parent = (
        _parent_path(source)
        if source
        else ""
    )

    destination_parent = (
        _parent_path(destination)
        if destination
        else ""
    )

    common = {
        "actor": request.user,
        "team": team,
        "accion": accion,
        "tipo_elemento": tipo_elemento,
        "url": str(url or "").strip(),
        "storage_provider": "nextcloud",
        "objeto": None,
        "tipo_objeto": (
            "archivos.cloud_folder"
            if is_folder
            else "archivos.cloud_file"
        ),
        "objeto_id": (
            snapshot.get("reference_ids", [None])[0]
            if snapshot.get("reference_ids")
            else None
        ),
        # Las referencias se usan para resolver el Team,
        # pero no son elementos creados, movidos,
        # renombrados o eliminados por esta operación.
        # No deben aparecer como lista visible en el dashboard.
        "nombres": [],
        "metadata_extra": {
            "remote_item_type": (
                "folder"
                if is_folder
                else "file"
            ),
            "remote_file_id": str(
                item.get("file_id")
                or ""
            ),
            "remote_etag": str(
                item.get("etag")
                or ""
            ),
            "source_path": source,
            "destination_path": destination,
            "reference_ids": (
                snapshot.get(
                    "reference_ids",
                    [],
                )[:100]
            ),
            "affected_reference_names": (
                snapshot.get(
                    "reference_names",
                    [],
                )[:100]
            ),
            "affected_reference_names_truncated": (
                len(
                    snapshot.get(
                        "reference_names",
                        [],
                    )
                )
                > 100
            ),
            "reference_count": int(
                snapshot.get(
                    "reference_count",
                    0,
                )
            ),
            "assigned_team_ids": (
                snapshot.get(
                    "assigned_team_ids",
                    [],
                )
            ),
            "unclassified_reference_count": int(
                snapshot.get(
                    "unclassified_count",
                    0,
                )
            ),
            "references_affected": int(
                references_affected or 0
            ),
            "team_resolution": team_resolution,
        },
        # P3_CLOUD_OPERATION_ID
        "operation_id": operation_id,

        # La operación remota y la actualización local
        # ya han terminado cuando se registra.
        "diferir_hasta_commit": False,
    }

    if accion == "crear_carpeta":
        return registrar_operacion_documental(
            **common,
            nombre=(
                destination_name
                or source_name
            ),
            ruta_destino=(
                destination_parent
                or "Archivos"
            ),
        )

    if accion == "renombrar":
        return registrar_operacion_documental(
            **common,
            nombre_anterior=source_name,
            nombre_nuevo=(
                destination_name
                or source_name
            ),
            ruta_origen=(
                source_parent
                or "Archivos"
            ),
            ruta_destino=(
                destination_parent
                or "Archivos"
            ),
        )

    if accion == "mover":
        return registrar_operacion_documental(
            **common,
            nombre=(
                destination_name
                or source_name
            ),
            ruta_origen=(
                source_parent
                or "Archivos"
            ),
            ruta_destino=(
                destination_parent
                or "Archivos"
            ),
        )

    if accion == "eliminar":
        return registrar_operacion_documental(
            **common,
            nombre=source_name,
            ruta_origen=(
                source_parent
                or "Archivos"
            ),
        )

    raise ValueError(
        "Acción cloud no soportada."
    )
