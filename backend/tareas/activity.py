from __future__ import annotations

from actividad.models import (
    ActividadPlataforma,
)
from actividad.services import (
    registrar_actividad,
)


STATE_LABELS = {
    "pendiente": "Pendiente",
    "en_curso": "En curso",
    "bloqueada": "Bloqueada",
    "hecha": "Hecha",
}

PRIORITY_LABELS = {
    "baja": "Baja",
    "media": "Media",
    "alta": "Alta",
}

SIGNIFICANT_FIELDS = (
    "titulo",
    "descripcion",
    "estado",
    "prioridad",
    "vencimiento",
    "etiquetas",
    "visibilidad",
    "asignado_ids",
)


def _serialize(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()

    return value


def _state_label(value):
    value = str(value or "").strip()

    return STATE_LABELS.get(
        value,
        value.replace("_", " ").capitalize(),
    )


def _priority_label(value):
    value = str(value or "").strip()

    return PRIORITY_LABELS.get(
        value,
        value.replace("_", " ").capitalize(),
    )


def _task_title(task):
    title = str(
        getattr(task, "titulo", "")
        or ""
    ).strip()

    return title or f"Tarea #{task.pk}"


def _assigned_snapshot(task):
    rows = []

    for user in (
        task.asignados
        .all()
        .order_by("pk")
    ):
        display_name = (
            user.get_full_name()
            or user.username
        )

        rows.append({
            "id": user.pk,
            "username": user.username,
            "nombre": display_name,
        })

    return rows


def snapshot_tarea(task):
    """Captura únicamente datos funcionales comparables."""
    if not getattr(task, "pk", None):
        raise ValueError(
            "La tarea debe estar guardada."
        )

    assigned = _assigned_snapshot(task)

    return {
        "tarea_id": task.pk,
        "team_id": task.team_id,
        "titulo": _task_title(task),
        "descripcion": str(
            task.descripcion or ""
        ),
        "estado": str(
            task.estado or ""
        ),
        "estado_label": _state_label(
            task.estado
        ),
        "prioridad": str(
            task.prioridad or ""
        ),
        "prioridad_label": _priority_label(
            task.prioridad
        ),
        "vencimiento": _serialize(
            task.vencimiento
        ),
        "etiquetas": str(
            task.etiquetas or ""
        ),
        "visibilidad": str(
            task.visibilidad or ""
        ),
        "asignado_ids": [
            row["id"]
            for row in assigned
        ],
        "asignados": assigned,
        "actualizado": _serialize(
            task.actualizado
        ),
    }


def _activity_visibility(task):
    if (
        task.team_id
        and task.visibilidad
        in {
            "depto",
            "global",
        }
    ):
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


def _grouping_key(
    *,
    action,
    task,
    actor,
):
    return (
        f"tareas:{action}:"
        f"{task.team_id or ''}:"
        f"{getattr(actor, 'pk', '')}"
    )


def _common_metadata(snapshot):
    return {
        "tarea_id": snapshot["tarea_id"],
        "team_id": snapshot["team_id"],
        "titulo": snapshot["titulo"],
        "estado": snapshot["estado"],
        "estado_label": (
            snapshot["estado_label"]
        ),
        "prioridad": snapshot["prioridad"],
        "prioridad_label": (
            snapshot["prioridad_label"]
        ),
        "vencimiento": snapshot[
            "vencimiento"
        ],
        "visibilidad_tarea": snapshot[
            "visibilidad"
        ],
        "asignado_ids": snapshot[
            "asignado_ids"
        ],
        "asignados": snapshot[
            "asignados"
        ],
    }


def registrar_creacion_tarea(
    *,
    tarea,
    actor,
    diferir_hasta_commit=True,
):
    """
    Registra una sola actividad por alta funcional.

    No se invoca desde señales, imports ni guardados ORM.
    """
    snapshot = snapshot_tarea(tarea)
    title = snapshot["titulo"]

    metadata = _common_metadata(
        snapshot
    )

    metadata.update({
        "operacion": "creacion",
        "campos_cambiados": [],
    })

    return registrar_actividad(
        modulo="tareas",
        accion="crear_tarea",
        actor=actor,
        team=tarea.team,
        objeto=tarea,
        objeto_repr=(
            f"Tarea · {title}"
        ),
        descripcion=(
            f'ha creado la tarea «{title}».'
        ),
        url="/app/tareas/",
        visibilidad=(
            _activity_visibility(tarea)
        ),
        origen=(
            ActividadPlataforma
            .Origen
            .EXPLICITO
        ),
        metadata=metadata,
        agrupacion_key=(
            _grouping_key(
                action="crear_tarea",
                task=tarea,
                actor=actor,
            )
        ),
        clave_idempotencia=(
            f"tareas:crear:{tarea.pk}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )


def _changed_fields(
    previous,
    current,
):
    return [
        field
        for field in SIGNIFICANT_FIELDS
        if previous.get(field)
        != current.get(field)
    ]


def _change_action(
    *,
    previous,
    current,
    changed_fields,
):
    if (
        "estado" in changed_fields
        and current["estado"] == "hecha"
    ):
        return "completar_tarea"

    if "estado" in changed_fields:
        return "cambiar_estado_tarea"

    if "asignado_ids" in changed_fields:
        return "reasignar_tarea"

    return "editar_tarea"


def _change_description(
    *,
    action,
    previous,
    current,
):
    title = current["titulo"]

    if action == "completar_tarea":
        return (
            f'ha completado la tarea '
            f'«{title}».'
        )

    if action == "cambiar_estado_tarea":
        return (
            f'ha cambiado el estado de la tarea '
            f'«{title}» de '
            f'«{previous["estado_label"]}» a '
            f'«{current["estado_label"]}».'
        )

    if action == "reasignar_tarea":
        return (
            f'ha actualizado los responsables '
            f'de la tarea «{title}».'
        )

    return (
        f'ha actualizado la tarea '
        f'«{title}».'
    )


def registrar_cambio_tarea(
    *,
    tarea,
    actor,
    anterior,
    diferir_hasta_commit=True,
):
    """
    Registra como máximo una actividad por edición.

    Prioridad semántica:
    completar > cambiar estado > reasignar > editar.
    """
    if not isinstance(anterior, dict):
        raise TypeError(
            "El estado anterior debe ser un diccionario."
        )

    current = snapshot_tarea(tarea)

    changed_fields = _changed_fields(
        anterior,
        current,
    )

    if not changed_fields:
        return None

    action = _change_action(
        previous=anterior,
        current=current,
        changed_fields=changed_fields,
    )

    changes = {
        field: {
            "anterior": anterior.get(field),
            "actual": current.get(field),
        }
        for field in changed_fields
    }

    metadata = _common_metadata(
        current
    )

    metadata.update({
        "operacion": "edicion",
        "accion_funcional": action,
        "campos_cambiados": changed_fields,
        "cambios": changes,
        "estado_anterior": anterior.get(
            "estado"
        ),
        "estado_anterior_label": (
            anterior.get(
                "estado_label"
            )
        ),
        "asignado_ids_anteriores": (
            anterior.get(
                "asignado_ids",
                [],
            )
        ),
        "asignados_anteriores": (
            anterior.get(
                "asignados",
                [],
            )
        ),
    })

    update_token = (
        current.get("actualizado")
        or tarea.pk
    )

    return registrar_actividad(
        modulo="tareas",
        accion=action,
        actor=actor,
        team=tarea.team,
        objeto=tarea,
        objeto_repr=(
            f'Tarea · {current["titulo"]}'
        ),
        descripcion=(
            _change_description(
                action=action,
                previous=anterior,
                current=current,
            )
        ),
        url="/app/tareas/",
        visibilidad=(
            _activity_visibility(tarea)
        ),
        origen=(
            ActividadPlataforma
            .Origen
            .EXPLICITO
        ),
        metadata=metadata,
        agrupacion_key=(
            _grouping_key(
                action=action,
                task=tarea,
                actor=actor,
            )
        ),
        clave_idempotencia=(
            f"tareas:{action}:"
            f"{tarea.pk}:{update_token}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )
