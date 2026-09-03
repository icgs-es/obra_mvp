from __future__ import annotations

import uuid
from typing import Any, Iterable

from django.urls import (
    NoReverseMatch,
    reverse,
)

from actividad.services import (
    registrar_actividad,
)


MODULE = "planificacion_obra"
VISIBILITY = "EQUIPO"


FUNCTIONAL_FIELDS = (
    "empleado_id",
    "tarea_obra_id",
    "unidad_obra_id",
    "capitulo_id",
    "partida_id",
    "fecha_inicio",
    "hora_inicio",
    "fecha_fin",
    "hora_fin",
    "estado",
    "observaciones",
)


EMPLOYEE_FIELDS = {
    "empleado_id",
}


DESTINATION_FIELDS = {
    "tarea_obra_id",
    "unidad_obra_id",
    "capitulo_id",
    "partida_id",
}


TEMPORAL_FIELDS = {
    "fecha_inicio",
    "hora_inicio",
    "fecha_fin",
    "hora_fin",
}


def _serialize(value):
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return value


def _assignment_url(
    assignment_id=None,
):
    if assignment_id:
        route_names = (
            (
                "planificacion_obra:"
                "asignacion_detail"
            ),
            (
                "planificacion:"
                "asignacion_detail"
            ),
        )

        for route_name in route_names:
            try:
                return reverse(
                    route_name,
                    args=[assignment_id],
                )

            except NoReverseMatch:
                continue

    route_names = (
        (
            "planificacion_obra:"
            "asignaciones_list"
        ),
        (
            "planificacion:"
            "asignaciones_list"
        ),
    )

    for route_name in route_names:
        try:
            return reverse(route_name)

        except NoReverseMatch:
            continue

    return (
        "/app/planificacion/"
        "asignaciones/"
    )


def snapshot_asignacion(
    asignacion,
) -> dict[str, Any]:
    empleado = asignacion.empleado

    rrhh_empleado = empleado

    tarea = asignacion.tarea_obra
    unidad = asignacion.unidad_obra
    capitulo = asignacion.capitulo
    partida = asignacion.partida

    obra = None

    if (
        tarea is not None
        and tarea.obra_id
    ):
        obra = tarea.obra

    elif (
        unidad is not None
        and unidad.obra_id
    ):
        obra = unidad.obra

    return {
        "id": asignacion.pk,
        "team_id": asignacion.team_id,

        "empleado_id": (
            asignacion.empleado_id
        ),
        "empleado_nombre": (
            empleado.nombre_completo
        ),
        "rrhh_empleado_id": (
            rrhh_empleado.pk
        ),
        "usuario_afectado_id": (
            rrhh_empleado.user_id
        ),

        "obra_id": (
            obra.pk
            if obra is not None
            else None
        ),
        "obra_nombre": (
            obra.nombre
            if obra is not None
            else ""
        ),

        "tarea_obra_id": (
            asignacion.tarea_obra_id
        ),
        "unidad_obra_id": (
            asignacion.unidad_obra_id
        ),
        "capitulo_id": (
            asignacion.capitulo_id
        ),
        "partida_id": (
            asignacion.partida_id
        ),

        "unidad_obra_repr": (
            str(unidad)
            if unidad is not None
            else ""
        ),
        "capitulo_codigo": (
            capitulo.codigo
            if capitulo is not None
            else ""
        ),
        "capitulo_nombre": (
            capitulo.nombre
            if capitulo is not None
            else ""
        ),
        "partida_codigo": (
            partida.codigo
            if partida is not None
            else ""
        ),
        "partida_nombre": (
            partida.nombre
            if partida is not None
            else ""
        ),

        "fecha_inicio": _serialize(
            asignacion.fecha_inicio
        ),
        "hora_inicio": _serialize(
            asignacion.hora_inicio
        ),
        "fecha_fin": _serialize(
            asignacion.fecha_fin
        ),
        "hora_fin": _serialize(
            asignacion.hora_fin
        ),

        "estado": asignacion.estado,
        "observaciones": (
            asignacion.observaciones
            or ""
        ),

        "creado_por_id": (
            asignacion.creado_por_id
        ),
        "creado_en": _serialize(
            asignacion.creado_en
        ),
        "actualizado_en": _serialize(
            asignacion.actualizado_en
        ),
    }


def _changed_fields(
    anterior,
    actual,
):
    return [
        field_name
        for field_name in FUNCTIONAL_FIELDS
        if anterior.get(field_name)
        != actual.get(field_name)
    ]


def _affected_user_ids(
    *snapshots,
):
    values = {
        snapshot.get(
            "usuario_afectado_id"
        )
        for snapshot in snapshots
        if snapshot
        and snapshot.get(
            "usuario_afectado_id"
        )
    }

    return sorted(values)


def _destination_text(
    snapshot,
):
    parts = []

    obra_nombre = snapshot.get(
        "obra_nombre"
    )

    if obra_nombre:
        parts.append(
            f"la obra «{obra_nombre}»"
        )

    partida_codigo = snapshot.get(
        "partida_codigo"
    )

    partida_nombre = snapshot.get(
        "partida_nombre"
    )

    if partida_codigo or partida_nombre:
        partida = " ".join(
            value
            for value in (
                partida_codigo,
                partida_nombre,
            )
            if value
        )

        parts.append(
            f"la partida «{partida}»"
        )

    unidad = snapshot.get(
        "unidad_obra_repr"
    )

    if unidad:
        parts.append(
            f"la unidad «{unidad}»"
        )

    if not parts:
        return "la planificación de obra"

    return ", ".join(parts)


def _period_text(
    snapshot,
):
    inicio = " ".join(
        value
        for value in (
            snapshot.get(
                "fecha_inicio"
            ),
            snapshot.get(
                "hora_inicio"
            ),
        )
        if value
    )

    fin = " ".join(
        value
        for value in (
            snapshot.get(
                "fecha_fin"
            ),
            snapshot.get(
                "hora_fin"
            ),
        )
        if value
    )

    if inicio and fin:
        return (
            f" desde {inicio} "
            f"hasta {fin}"
        )

    if inicio:
        return f" desde {inicio}"

    return ""


def _base_metadata(
    snapshot,
):
    return {
        "asignacion_id": (
            snapshot.get("id")
        ),
        "team_id": (
            snapshot.get("team_id")
        ),

        "empleado_id": (
            snapshot.get(
                "empleado_id"
            )
        ),
        "empleado_nombre": (
            snapshot.get(
                "empleado_nombre"
            )
        ),
        "rrhh_empleado_id": (
            snapshot.get(
                "rrhh_empleado_id"
            )
        ),
        "usuario_afectado_id": (
            snapshot.get(
                "usuario_afectado_id"
            )
        ),
        "usuarios_afectados_ids": (
            _affected_user_ids(
                snapshot
            )
        ),

        "obra_id": (
            snapshot.get("obra_id")
        ),
        "obra_nombre": (
            snapshot.get(
                "obra_nombre"
            )
        ),

        "tarea_obra_id": (
            snapshot.get(
                "tarea_obra_id"
            )
        ),
        "unidad_obra_id": (
            snapshot.get(
                "unidad_obra_id"
            )
        ),
        "capitulo_id": (
            snapshot.get(
                "capitulo_id"
            )
        ),
        "partida_id": (
            snapshot.get(
                "partida_id"
            )
        ),

        "capitulo_codigo": (
            snapshot.get(
                "capitulo_codigo"
            )
        ),
        "partida_codigo": (
            snapshot.get(
                "partida_codigo"
            )
        ),

        "fecha_inicio": (
            snapshot.get(
                "fecha_inicio"
            )
        ),
        "hora_inicio": (
            snapshot.get(
                "hora_inicio"
            )
        ),
        "fecha_fin": (
            snapshot.get(
                "fecha_fin"
            )
        ),
        "hora_fin": (
            snapshot.get(
                "hora_fin"
            )
        ),

        "estado": (
            snapshot.get("estado")
        ),
    }


def registrar_creacion_asignacion(
    *,
    asignacion,
    actor,
    fuente="formulario",
    operation_id=None,
    recurso_real_ids=None,
    estado_sync=None,
    diferir_hasta_commit=True,
):
    snapshot = snapshot_asignacion(
        asignacion
    )

    recurso_real_ids = list(
        recurso_real_ids or []
    )

    descripcion = (
        "ha asignado a "
        f"«{snapshot['empleado_nombre']}» "
        f"a {_destination_text(snapshot)}"
        f"{_period_text(snapshot)}."
    )

    metadata = _base_metadata(
        snapshot
    )

    metadata.update({
        "fuente": fuente,
        "operation_id": operation_id,
        "estado_sync": estado_sync,
        "recurso_real_ids": (
            recurso_real_ids
        ),
        "recurso_real_derivado": bool(
            recurso_real_ids
        ),
        (
            "suprimir_actividad_"
            "recurso_real_derivado"
        ): True,
    })

    return registrar_actividad(
        team=asignacion.team,
        actor=actor,
        modulo=MODULE,
        accion=(
            "asignar_personal_obra"
        ),
        tipo_objeto=(
            asignacion
            ._meta
            .label_lower
        ),
        objeto_id=asignacion.pk,
        objeto_repr=(
            snapshot[
                "empleado_nombre"
            ]
        ),
        descripcion=descripcion,
        url=_assignment_url(
            asignacion.pk
        ),
        visibilidad=VISIBILITY,
        origen="EXPLICITO",
        metadata=metadata,
        agrupacion_key=(
            "planificacion_obra:"
            "asignar_personal:"
            f"{asignacion.pk}"
        ),
        clave_idempotencia=(
            "planificacion_obra:"
            "asignacion:crear:"
            f"{asignacion.pk}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )


def _action_for_change(
    *,
    anterior,
    actual,
    campos_cambiados,
):
    changed = set(
        campos_cambiados
    )

    if not changed:
        return None

    if (
        "estado" in changed
        and actual.get("estado")
        == "REALIZADO"
    ):
        return (
            "realizar_asignacion_personal"
        )

    if changed & EMPLOYEE_FIELDS:
        return (
            "reasignar_personal_obra"
        )

    if changed & DESTINATION_FIELDS:
        return (
            "cambiar_destino_"
            "asignacion_personal"
        )

    if changed & TEMPORAL_FIELDS:
        return (
            "reprogramar_"
            "asignacion_personal"
        )

    if "estado" in changed:
        return (
            "cambiar_estado_"
            "asignacion_personal"
        )

    return (
        "editar_asignacion_personal"
    )


def _description_for_change(
    *,
    accion,
    anterior,
    actual,
):
    empleado = actual.get(
        "empleado_nombre"
    ) or anterior.get(
        "empleado_nombre"
    )

    if (
        accion
        == "realizar_asignacion_personal"
    ):
        return (
            "ha marcado como realizada "
            "la asignación de "
            f"«{empleado}» en "
            f"{_destination_text(actual)}."
        )

    if (
        accion
        == "reasignar_personal_obra"
    ):
        return (
            "ha sustituido a "
            f"«{anterior.get('empleado_nombre')}» "
            "por "
            f"«{actual.get('empleado_nombre')}» "
            f"en {_destination_text(actual)}."
        )

    if (
        accion
        == (
            "cambiar_destino_"
            "asignacion_personal"
        )
    ):
        return (
            "ha cambiado el destino "
            "de la asignación de "
            f"«{empleado}» a "
            f"{_destination_text(actual)}."
        )

    if (
        accion
        == (
            "reprogramar_"
            "asignacion_personal"
        )
    ):
        return (
            "ha reprogramado la asignación "
            f"de «{empleado}»"
            f"{_period_text(actual)}."
        )

    if (
        accion
        == (
            "cambiar_estado_"
            "asignacion_personal"
        )
    ):
        return (
            "ha cambiado el estado "
            "de la asignación de "
            f"«{empleado}» a "
            f"«{actual.get('estado')}»."
        )

    return (
        "ha actualizado la asignación "
        f"de «{empleado}»."
    )


def registrar_cambio_asignacion(
    *,
    asignacion,
    actor,
    anterior,
    fuente="formulario",
    operation_id=None,
    recurso_real_ids=None,
    recurso_real_anteriores_ids=None,
    diferir_hasta_commit=True,
):
    actual = snapshot_asignacion(
        asignacion
    )

    campos_cambiados = _changed_fields(
        anterior,
        actual,
    )

    accion = _action_for_change(
        anterior=anterior,
        actual=actual,
        campos_cambiados=(
            campos_cambiados
        ),
    )

    if accion is None:
        return None

    recurso_real_ids = list(
        recurso_real_ids or []
    )

    recurso_real_anteriores_ids = list(
        recurso_real_anteriores_ids
        or []
    )

    recurso_real_creados_ids = sorted(
        set(recurso_real_ids)
        - set(
            recurso_real_anteriores_ids
        )
    )

    recurso_real_eliminados_ids = sorted(
        set(
            recurso_real_anteriores_ids
        )
        - set(recurso_real_ids)
    )

    metadata = _base_metadata(
        actual
    )

    metadata.update({
        "fuente": fuente,
        "operation_id": operation_id,
        "campos_cambiados": (
            campos_cambiados
        ),
        "valores_anteriores": {
            field_name: anterior.get(
                field_name
            )
            for field_name
            in campos_cambiados
        },
        "valores_actuales": {
            field_name: actual.get(
                field_name
            )
            for field_name
            in campos_cambiados
        },
        "empleado_anterior_id": (
            anterior.get(
                "empleado_id"
            )
        ),
        "empleado_anterior_nombre": (
            anterior.get(
                "empleado_nombre"
            )
        ),
        "usuario_afectado_anterior_id": (
            anterior.get(
                "usuario_afectado_id"
            )
        ),
        "usuarios_afectados_ids": (
            _affected_user_ids(
                anterior,
                actual,
            )
        ),
        "estado_anterior": (
            anterior.get("estado")
        ),
        "recurso_real_ids": (
            recurso_real_ids
        ),
        "recurso_real_anteriores_ids": (
            recurso_real_anteriores_ids
        ),
        "recurso_real_creados_ids": (
            recurso_real_creados_ids
        ),
        "recurso_real_eliminados_ids": (
            recurso_real_eliminados_ids
        ),
        "recurso_real_derivado": bool(
            recurso_real_ids
        ),
        (
            "suprimir_actividad_"
            "recurso_real_derivado"
        ): True,
    })

    revision = (
        operation_id
        or actual.get(
            "actualizado_en"
        )
        or uuid.uuid4().hex
    )

    return registrar_actividad(
        team=asignacion.team,
        actor=actor,
        modulo=MODULE,
        accion=accion,
        tipo_objeto=(
            asignacion
            ._meta
            .label_lower
        ),
        objeto_id=asignacion.pk,
        objeto_repr=(
            actual[
                "empleado_nombre"
            ]
        ),
        descripcion=(
            _description_for_change(
                accion=accion,
                anterior=anterior,
                actual=actual,
            )
        ),
        url=_assignment_url(
            asignacion.pk
        ),
        visibilidad=VISIBILITY,
        origen="EXPLICITO",
        metadata=metadata,
        agrupacion_key=(
            "planificacion_obra:"
            f"{accion}:"
            f"{asignacion.pk}"
        ),
        clave_idempotencia=(
            "planificacion_obra:"
            f"{accion}:"
            f"{asignacion.pk}:"
            f"{revision}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )


def registrar_realizacion_asignacion(
    *,
    asignacion,
    actor,
    anterior,
    recurso_real_ids=None,
    recurso_real_creados=0,
    recurso_real_actualizados=0,
    fuente="accion_realizar",
    operation_id=None,
    diferir_hasta_commit=True,
):
    actual = snapshot_asignacion(
        asignacion
    )

    recurso_real_ids = list(
        recurso_real_ids or []
    )

    operation_id = (
        operation_id
        or uuid.uuid4().hex
    )

    metadata = _base_metadata(
        actual
    )

    metadata.update({
        "fuente": fuente,
        "operation_id": operation_id,
        "estado_anterior": (
            anterior.get("estado")
        ),
        "estado": (
            actual.get("estado")
        ),
        "recurso_real_ids": (
            recurso_real_ids
        ),
        "recurso_real_creados": (
            recurso_real_creados
        ),
        "recurso_real_actualizados": (
            recurso_real_actualizados
        ),
        "recurso_real_derivado": bool(
            recurso_real_ids
        ),
        (
            "suprimir_actividad_"
            "recurso_real_derivado"
        ): True,
        "usuarios_afectados_ids": (
            _affected_user_ids(
                anterior,
                actual,
            )
        ),
    })

    return registrar_actividad(
        team=asignacion.team,
        actor=actor,
        modulo=MODULE,
        accion=(
            "realizar_asignacion_personal"
        ),
        tipo_objeto=(
            asignacion
            ._meta
            .label_lower
        ),
        objeto_id=asignacion.pk,
        objeto_repr=(
            actual[
                "empleado_nombre"
            ]
        ),
        descripcion=(
            "ha marcado como realizada "
            "la asignación de "
            f"«{actual['empleado_nombre']}» "
            f"en {_destination_text(actual)}."
        ),
        url=_assignment_url(
            asignacion.pk
        ),
        visibilidad=VISIBILITY,
        origen="EXPLICITO",
        metadata=metadata,
        agrupacion_key=(
            "planificacion_obra:"
            "realizar_asignacion:"
            f"{asignacion.pk}"
        ),
        clave_idempotencia=(
            "planificacion_obra:"
            "asignacion:realizar:"
            f"{asignacion.pk}:"
            f"{operation_id}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )


def registrar_eliminacion_asignacion(
    *,
    asignacion,
    actor,
    anterior=None,
    fuente="formulario",
    operation_id=None,
    recurso_real_eliminados_ids=None,
    recurso_real_relacionados_ids=None,
    diferir_hasta_commit=True,
):
    anterior = (
        anterior
        or snapshot_asignacion(
            asignacion
        )
    )

    operation_id = (
        operation_id
        or anterior.get(
            "actualizado_en"
        )
        or anterior.get(
            "creado_en"
        )
        or uuid.uuid4().hex
    )

    recurso_real_eliminados_ids = list(
        recurso_real_eliminados_ids
        or []
    )

    recurso_real_relacionados_ids = list(
        recurso_real_relacionados_ids
        or []
    )

    metadata = _base_metadata(
        anterior
    )

    metadata.update({
        "fuente": fuente,
        "operation_id": operation_id,
        "recurso_real_eliminados_ids": (
            recurso_real_eliminados_ids
        ),
        "recurso_real_relacionados_ids": (
            recurso_real_relacionados_ids
        ),
        (
            "suprimir_actividad_"
            "recurso_real_derivado"
        ): True,
    })

    return registrar_actividad(
        team=asignacion.team,
        actor=actor,
        modulo=MODULE,
        accion=(
            "eliminar_asignacion_personal"
        ),
        tipo_objeto=(
            asignacion
            ._meta
            .label_lower
        ),
        objeto_id=anterior["id"],
        objeto_repr=(
            anterior[
                "empleado_nombre"
            ]
        ),
        descripcion=(
            "ha eliminado la asignación "
            f"de «{anterior['empleado_nombre']}» "
            f"en {_destination_text(anterior)}."
        ),
        url=_assignment_url(),
        visibilidad=VISIBILITY,
        origen="EXPLICITO",
        metadata=metadata,
        agrupacion_key=(
            "planificacion_obra:"
            "eliminar_asignacion:"
            f"{anterior['id']}"
        ),
        clave_idempotencia=(
            "planificacion_obra:"
            "asignacion:eliminar:"
            f"{anterior['id']}:"
            f"{operation_id}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )


def registrar_repeticion_asignaciones(
    *,
    asignaciones: Iterable,
    actor,
    asignacion_origen_id=None,
    fuente="repetir",
    operation_id=None,
    recurso_real_ids=None,
    estado_sync=None,
    diferir_hasta_commit=True,
):
    asignaciones = list(
        asignaciones or []
    )

    if not asignaciones:
        return None

    snapshots = [
        snapshot_asignacion(
            asignacion
        )
        for asignacion in asignaciones
    ]

    first_assignment = (
        asignaciones[0]
    )

    first_snapshot = snapshots[0]

    assignment_ids = [
        snapshot["id"]
        for snapshot in snapshots
    ]

    employee_names = sorted({
        snapshot[
            "empleado_nombre"
        ]
        for snapshot in snapshots
    })

    operation_id = (
        operation_id
        or uuid.uuid4().hex
    )

    recurso_real_ids = list(
        recurso_real_ids or []
    )

    quantity = len(
        assignments := assignment_ids
    )

    if (
        len(employee_names) == 1
    ):
        employee_text = (
            f"«{employee_names[0]}»"
        )

    else:
        employee_text = (
            f"{len(employee_names)} "
            "personas"
        )

    descripcion = (
        "ha repetido la asignación "
        f"de {employee_text} en "
        f"{quantity} "
        f"{'fecha' if quantity == 1 else 'fechas'}."
    )

    metadata = {
        "fuente": fuente,
        "operation_id": operation_id,
        "estado_sync": estado_sync,
        "recurso_real_ids": (
            recurso_real_ids
        ),
        "recurso_real_derivado": bool(
            recurso_real_ids
        ),
        "asignacion_origen_id": (
            asignacion_origen_id
        ),
        "asignacion_ids": assignments,
        "cantidad": quantity,
        "empleado_ids": sorted({
            snapshot[
                "empleado_id"
            ]
            for snapshot in snapshots
        }),
        "empleados_nombres": (
            employee_names
        ),
        "usuarios_afectados_ids": (
            _affected_user_ids(
                *snapshots
            )
        ),
        "obra_ids": sorted({
            snapshot["obra_id"]
            for snapshot in snapshots
            if snapshot["obra_id"]
        }),
        "tarea_obra_ids": sorted({
            snapshot[
                "tarea_obra_id"
            ]
            for snapshot in snapshots
            if snapshot[
                "tarea_obra_id"
            ]
        }),
        "periodos": [
            {
                "asignacion_id": (
                    snapshot["id"]
                ),
                "fecha_inicio": (
                    snapshot[
                        "fecha_inicio"
                    ]
                ),
                "hora_inicio": (
                    snapshot[
                        "hora_inicio"
                    ]
                ),
                "fecha_fin": (
                    snapshot[
                        "fecha_fin"
                    ]
                ),
                "hora_fin": (
                    snapshot[
                        "hora_fin"
                    ]
                ),
            }
            for snapshot in snapshots
        ],
        (
            "suprimir_actividad_"
            "recurso_real_derivado"
        ): True,
    }

    return registrar_actividad(
        team=first_assignment.team,
        actor=actor,
        modulo=MODULE,
        accion=(
            "repetir_asignacion_personal"
        ),
        tipo_objeto=(
            "planificacion_obra."
            "asignacion_repeticion"
        ),
        objeto_id=(
            asignacion_origen_id
        ),
        objeto_repr=(
            f"{quantity} asignaciones"
        ),
        descripcion=descripcion,
        url=_assignment_url(),
        visibilidad=VISIBILITY,
        origen="EXPLICITO",
        metadata=metadata,
        agrupacion_key=(
            "planificacion_obra:"
            "repetir_asignaciones:"
            f"{operation_id}"
        ),
        clave_idempotencia=(
            "planificacion_obra:"
            "asignaciones:repetir:"
            f"{operation_id}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )
