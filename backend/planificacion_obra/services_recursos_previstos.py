
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

from django.apps import apps
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from .activity import registrar_actividad


MODULO = 'planificacion_obra'
VISIBILIDAD = 'EQUIPO'
ORIGEN_ACTIVIDAD = 'EXPLICITO'


class PrevistoActionError(ValueError):
    pass


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    if isinstance(value, dict):
        return {
            str(key): _json_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            _json_value(item)
            for item in value
        ]

    return value


def snapshot_previsto(obj):
    if isinstance(obj, dict):
        return _json_value(
            deepcopy(obj)
        )

    raw = (
        deepcopy(obj.raw_data)
        if isinstance(
            getattr(
                obj,
                "raw_data",
                None,
            ),
            dict,
        )
        else {}
    )

    tarea = getattr(
        obj,
        "tarea_obra",
        None,
    )

    recurso = getattr(
        obj,
        "recurso",
        None,
    )

    return _json_value({
        "id": getattr(obj, "pk", None),
        "team_id": getattr(
            obj,
            "team_id",
            None,
        ),
        "tarea_obra_id": getattr(
            obj,
            "tarea_obra_id",
            None,
        ),
        "unidad_obra_id": getattr(
            obj,
            "unidad_obra_id",
            None,
        ),
        "partida_id": getattr(
            obj,
            "partida_id",
            None,
        ),
        "recurso_id": getattr(
            obj,
            "recurso_id",
            None,
        ),
        "tarea_repr": (
            str(tarea)
            if tarea is not None
            else ""
        ),
        "recurso_repr": (
            str(recurso)
            if recurso is not None
            else ""
        ),
        "legacy_id_recurso": getattr(
            obj,
            "legacy_id_recurso",
            None,
        ),
        "legacy_cod_obra": getattr(
            obj,
            "legacy_cod_obra",
            None,
        ),
        "legacy_cod_fase": getattr(
            obj,
            "legacy_cod_fase",
            None,
        ),
        "legacy_cod_vivienda": getattr(
            obj,
            "legacy_cod_vivienda",
            "",
        ),
        "legacy_planta": getattr(
            obj,
            "legacy_planta",
            "",
        ),
        "legacy_cod_partida": getattr(
            obj,
            "legacy_cod_partida",
            "",
        ),
        "unidad": getattr(
            obj,
            "unidad",
            "",
        ),
        "cantidad": getattr(
            obj,
            "cantidad",
            None,
        ),
        "precio_unidad": getattr(
            obj,
            "precio_unidad",
            None,
        ),
        "costo_recurso": getattr(
            obj,
            "costo_recurso",
            None,
        ),
        "fecha_estimada_entrega": (
            getattr(
                obj,
                "fecha_estimada_entrega",
                None,
            )
        ),
        "control_suministros": (
            getattr(
                obj,
                "control_suministros",
                None,
            )
        ),
        "raw_data": raw,
        "origen": raw.get("origen"),
    })


BUSINESS_FIELDS = (
    "tarea_obra_id",
    "unidad_obra_id",
    "partida_id",
    "recurso_id",
    "legacy_id_recurso",
    "legacy_cod_obra",
    "legacy_cod_fase",
    "legacy_cod_vivienda",
    "legacy_planta",
    "legacy_cod_partida",
    "unidad",
    "cantidad",
    "precio_unidad",
    "costo_recurso",
    "fecha_estimada_entrega",
    "control_suministros",
)


def diff_previsto(previous, current):
    before = snapshot_previsto(
        previous
    )

    after = snapshot_previsto(
        current
    )

    changes = {}

    for field in BUSINESS_FIELDS:
        if before.get(field) == after.get(
            field
        ):
            continue

        changes[field] = {
            "before": before.get(field),
            "after": after.get(field),
        }

    return changes


def task_snapshot(task):
    unidad = task.unidad_obra
    obra = task.obra
    partida = task.partida

    return {
        "task_id": task.pk,
        "team_id": task.team_id,
        "obra_id": task.obra_id,
        "unidad_obra_id": (
            task.unidad_obra_id
        ),
        "partida_id": task.partida_id,
        "legacy_cod_obra": (
            getattr(
                task,
                "legacy_cod_obra",
                None,
            )
            or getattr(
                obra,
                "legacy_cod_obra",
                None,
            )
        ),
        "legacy_cod_fase": (
            getattr(
                task,
                "legacy_cod_fase",
                None,
            )
            or getattr(
                unidad,
                "legacy_cod_fase",
                None,
            )
        ),
        "legacy_cod_vivienda": (
            getattr(
                task,
                "legacy_cod_vivienda",
                None,
            )
            or getattr(
                unidad,
                "legacy_cod_vivienda",
                None,
            )
            or getattr(
                unidad,
                "vivienda",
                None,
            )
            or ""
        ),
        "legacy_planta": (
            getattr(
                task,
                "legacy_planta",
                "",
            )
            or ""
        ),
        "legacy_cod_partida": (
            getattr(
                task,
                "legacy_partida",
                "",
            )
            or getattr(
                partida,
                "codigo",
                "",
            )
            or ""
        ),
    }


def _object_repr(snapshot):
    return (
        snapshot.get("recurso_repr")
        or (
            "Recurso previsto "
            f"#{snapshot.get('id')}"
        )
    )[:255]


def _url(snapshot):
    task_id = snapshot.get(
        "tarea_obra_id"
    )

    if not task_id:
        return ""

    return reverse(
        (
            "planificacion_obra:"
            "planning_tarea_detail"
        ),
        args=[task_id],
    )


def _register(
    *,
    team,
    actor,
    audit_action,
    activity_action,
    object_id,
    object_repr,
    description,
    metadata,
    task_id,
    operation_id,
):
    Audit = apps.get_model(
        "gestion",
        "GestionAuditLog",
    )

    Audit.objects.create(
        team=team,
        usuario=actor,
        accion=audit_action,
        entidad=(
            "TareaRecursoPrevisto"
        ),
        objeto_id=object_id,
        objeto_repr=object_repr,
        descripcion=description,
        metadata=_json_value(
            metadata
        ),
    )

    url = (
        reverse(
            (
                "planificacion_obra:"
                "planning_tarea_detail"
            ),
            args=[task_id],
        )
        if task_id
        else ""
    )

    return registrar_actividad(
        modulo=MODULO,
        accion=activity_action,
        actor=actor,
        team=team,
        objeto=None,
        tipo_objeto=(
            "TareaRecursoPrevisto"
        ),
        objeto_id=object_id,
        objeto_repr=object_repr,
        descripcion=description,
        url=url,
        visibilidad=VISIBILIDAD,
        origen=ORIGEN_ACTIVIDAD,
        metadata=_json_value(
            metadata
        ),
        agrupacion_key=(
            "recurso_previsto:"
            f"{activity_action}:"
            f"{object_id}"
        ),
        clave_idempotencia=(
            "planificacion_obra:"
            "recurso_previsto:"
            f"{activity_action}:"
            f"{operation_id}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=True,
    )


def registrar_edicion_previsto(
    *,
    previsto,
    actor,
    anterior,
    operation_id,
):
    previous = snapshot_previsto(
        anterior
    )

    current = snapshot_previsto(
        previsto
    )

    changes = diff_previsto(
        previous,
        current,
    )

    if not changes:
        return None

    metadata = {
        "operation_id": operation_id,
        "recurso_previsto_id": (
            current["id"]
        ),
        "cambios": changes,
        "anterior": previous,
        "actual": current,
        "procedencia_conservada": True,
    }

    return _register(
        team=previsto.team,
        actor=actor,
        audit_action=(
            "EDITAR_RECURSO_PREVISTO"
        ),
        activity_action=(
            "editar_recurso_previsto"
        ),
        object_id=current["id"],
        object_repr=_object_repr(
            current
        ),
        description=(
            "Se actualizó un recurso "
            "previsto de Planning."
        ),
        metadata=metadata,
        task_id=current.get(
            "tarea_obra_id"
        ),
        operation_id=operation_id,
    )


def registrar_eliminacion_previsto(
    *,
    team,
    actor,
    anterior,
    operation_id,
):
    previous = snapshot_previsto(
        anterior
    )

    object_id = previous.get("id")

    if not object_id:
        raise PrevistoActionError(
            "No se pudo identificar el "
            "recurso previsto eliminado."
        )

    metadata = {
        "operation_id": operation_id,
        "recurso_previsto_id": (
            object_id
        ),
        "anterior": previous,
        "procedencia_conservada": True,
    }

    return _register(
        team=team,
        actor=actor,
        audit_action=(
            "ELIMINAR_RECURSO_PREVISTO"
        ),
        activity_action=(
            "eliminar_recurso_previsto"
        ),
        object_id=object_id,
        object_repr=_object_repr(
            previous
        ),
        description=(
            "Se eliminó un recurso "
            "previsto de Planning."
        ),
        metadata=metadata,
        task_id=previous.get(
            "tarea_obra_id"
        ),
        operation_id=operation_id,
    )


def _validate_relocation(
    previsto,
    target_task,
):
    source_task = previsto.tarea_obra

    if not source_task:
        raise PrevistoActionError(
            "El recurso previsto no tiene "
            "una tarea de origen."
        )

    if source_task.pk == target_task.pk:
        raise PrevistoActionError(
            "La tarea de destino coincide "
            "con la tarea actual."
        )

    if previsto.team_id != (
        target_task.team_id
    ):
        raise PrevistoActionError(
            "No se puede reubicar entre "
            "empresas diferentes."
        )

    if source_task.obra_id != (
        target_task.obra_id
    ):
        raise PrevistoActionError(
            "La tarea de destino debe "
            "pertenecer a la misma obra."
        )

    if source_task.partida_id != (
        target_task.partida_id
    ):
        raise PrevistoActionError(
            "La tarea de destino debe "
            "pertenecer a la misma partida."
        )

    if not target_task.unidad_obra_id:
        raise PrevistoActionError(
            "La tarea de destino no tiene "
            "vivienda o unidad de obra."
        )


@transaction.atomic
def execute_previsto_relocation(
    *,
    previsto_id,
    target_task_id,
    reason,
    user,
):
    reason = str(
        reason or ""
    ).strip()

    if len(reason) < 8:
        raise PrevistoActionError(
            "El motivo debe tener al "
            "menos 8 caracteres."
        )

    Prev = apps.get_model(
        "planificacion_obra",
        "TareaRecursoPrevisto",
    )

    Task = apps.get_model(
        "planificacion_obra",
        "TareaObra",
    )

    previsto = (
        Prev.objects
        .select_for_update(
            of=("self",)
        )
        .select_related(
            "team",
            "tarea_obra",
            "tarea_obra__obra",
            "tarea_obra__unidad_obra",
            "tarea_obra__partida",
            "recurso",
        )
        .get(pk=previsto_id)
    )

    target_task = (
        Task.objects
        .select_for_update(
            of=("self",)
        )
        .select_related(
            "team",
            "obra",
            "unidad_obra",
            "partida",
        )
        .get(pk=target_task_id)
    )

    _validate_relocation(
        previsto,
        target_task,
    )

    previous = snapshot_previsto(
        previsto
    )

    target = task_snapshot(
        target_task
    )

    operation_id = str(
        uuid4()
    )

    previsto.tarea_obra = target_task
    previsto.unidad_obra = (
        target_task.unidad_obra
    )
    previsto.partida = (
        target_task.partida
    )
    previsto.legacy_cod_obra = (
        target[
            "legacy_cod_obra"
        ]
    )
    previsto.legacy_cod_fase = (
        target[
            "legacy_cod_fase"
        ]
    )
    previsto.legacy_cod_vivienda = (
        str(
            target[
                "legacy_cod_vivienda"
            ]
            or ""
        )
    )
    previsto.legacy_planta = (
        str(
            target[
                "legacy_planta"
            ]
            or ""
        )
    )
    previsto.legacy_cod_partida = (
        str(
            target[
                "legacy_cod_partida"
            ]
            or ""
        )
    )

    raw = (
        deepcopy(
            previsto.raw_data
        )
        if isinstance(
            previsto.raw_data,
            dict,
        )
        else {}
    )

    history = raw.get(
        "reubicaciones",
        [],
    )

    if not isinstance(history, list):
        history = []

    event = {
        "operation_id": operation_id,
        "at": timezone.now().isoformat(),
        "user_id": getattr(
            user,
            "pk",
            None,
        ),
        "username": getattr(
            user,
            "username",
            "",
        ),
        "reason": reason,
        "before": previous,
        "target": target,
    }

    history.append(event)

    raw["reubicaciones"] = history
    raw[
        "ultima_reubicacion"
    ] = event

    previsto.raw_data = raw

    update_fields = [
        "tarea_obra",
        "unidad_obra",
        "partida",
        "legacy_cod_obra",
        "legacy_cod_fase",
        "legacy_cod_vivienda",
        "legacy_planta",
        "legacy_cod_partida",
        "raw_data",
    ]

    model_fields = {
        field.name
        for field in (
            previsto
            ._meta
            .concrete_fields
        )
    }

    if "updated_at" in model_fields:
        update_fields.append(
            "updated_at"
        )

    previsto.save(
        update_fields=update_fields
    )

    current = snapshot_previsto(
        previsto
    )

    metadata = {
        "operation_id": operation_id,
        "motivo": reason,
        "recurso_previsto_id": (
            previsto.pk
        ),
        "anterior": previous,
        "actual": current,
        "origen": {
            "task_id": previous.get(
                "tarea_obra_id"
            ),
            "unidad_obra_id": (
                previous.get(
                    "unidad_obra_id"
                )
            ),
        },
        "destino": target,
        "procedencia_conservada": True,
    }

    _register(
        team=previsto.team,
        actor=user,
        audit_action=(
            "REUBICAR_RECURSO_PREVISTO"
        ),
        activity_action=(
            "reubicar_recurso_previsto"
        ),
        object_id=previsto.pk,
        object_repr=_object_repr(
            current
        ),
        description=(
            "Se reubicó un recurso "
            "previsto de Planning."
        ),
        metadata=metadata,
        task_id=target_task.pk,
        operation_id=operation_id,
    )

    return {
        "operation_id": operation_id,
        "previsto_id": previsto.pk,
        "source_task_id": previous.get(
            "tarea_obra_id"
        ),
        "target_task_id": (
            target_task.pk
        ),
        "before": previous,
        "after": current,
    }
