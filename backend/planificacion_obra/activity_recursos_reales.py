from __future__ import annotations

from datetime import (
    date,
    datetime,
    time,
)
from decimal import Decimal
from typing import Any, Iterable

from django.apps import apps
from django.urls import (
    NoReverseMatch,
    reverse,
)

from .activity import registrar_actividad


MODULO = "planificacion_obra"
VISIBILIDAD = "EQUIPO"
ORIGEN_ACTIVIDAD = "EXPLICITO"

ORIGEN_MANUAL = "portal_manual"
CREADO_DESDE_MANUAL = (
    "tarea_recurso_real_create"
)

SOURCE_ASIGNACION = (
    "portal_asignacion_obra"
)
SOURCE_GESTION_PREFIX = (
    "portal_gestion"
)


CAMPOS_FUNCIONALES = (
    "tarea_obra_id",
    "unidad_obra_id",
    "partida_id",
    "recurso_id",
    "empleado_id",
    "movimiento_almacen_id",
    "unidad",
    "cantidad",
    "precio_unidad",
    "dias",
    "dias_reales",
    "horas",
    "horas_reales",
    "inicio_recurso_real",
    "fin_recurso_real",
    "costo_recurso",
    "costo_recurso_real",
    "id_proveedor",
    "cod_albaran",
    "num_linea_albaran",
    "cod_factura",
    "num_linea_factura",
    "observaciones",
)


CAMPOS_DESTINO = {
    "tarea_obra_id",
    "unidad_obra_id",
    "partida_id",
}


CAMPOS_RECURSO_PERSONA = {
    "recurso_id",
    "empleado_id",
}


CAMPOS_CANTIDAD_COSTE = {
    "unidad",
    "cantidad",
    "precio_unidad",
    "dias",
    "dias_reales",
    "horas",
    "horas_reales",
    "costo_recurso",
    "costo_recurso_real",
}


CAMPOS_FECHA = {
    "inicio_recurso_real",
    "fin_recurso_real",
}


def _valor_json(value: Any):
    if isinstance(
        value,
        (
            datetime,
            date,
            time,
        ),
    ):
        return value.isoformat()

    if isinstance(value, Decimal):
        return format(value, "f")

    if isinstance(value, dict):
        return {
            str(key): _valor_json(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        return [
            _valor_json(item)
            for item in value
        ]

    if isinstance(value, set):
        return sorted(
            _valor_json(item)
            for item in value
        )

    if hasattr(value, "pk"):
        return value.pk

    return value


def _raw_data(value: Any) -> dict:
    if isinstance(value, dict):
        raw = value.get("raw_data")

    else:
        raw = getattr(
            value,
            "raw_data",
            None,
        )

    if isinstance(raw, dict):
        return dict(raw)

    return {}


def _related_id(
    value: Any,
    relation_name: str,
):
    if isinstance(value, dict):
        return value.get(
            f"{relation_name}_id"
        )

    direct_name = (
        f"{relation_name}_id"
    )

    if hasattr(value, direct_name):
        return getattr(
            value,
            direct_name,
            None,
        )

    related = getattr(
        value,
        relation_name,
        None,
    )

    return getattr(
        related,
        "pk",
        None,
    )


def _repr_relation(
    value: Any,
    relation_name: str,
):
    if isinstance(value, dict):
        return value.get(
            f"{relation_name}_repr"
        )

    related = getattr(
        value,
        relation_name,
        None,
    )

    if related is None:
        return None

    return str(related)


def snapshot_recurso_real(
    recurso_real: Any,
) -> dict:
    if isinstance(recurso_real, dict):
        return _valor_json(
            dict(recurso_real)
        )

    raw = _raw_data(
        recurso_real
    )

    tarea = getattr(
        recurso_real,
        "tarea_obra",
        None,
    )

    obra = getattr(
        tarea,
        "obra",
        None,
    )

    snapshot = {
        "id": getattr(
            recurso_real,
            "pk",
            None,
        ),
        "team_id": _related_id(
            recurso_real,
            "team",
        ),
        "tarea_obra_id": _related_id(
            recurso_real,
            "tarea_obra",
        ),
        "unidad_obra_id": _related_id(
            recurso_real,
            "unidad_obra",
        ),
        "partida_id": _related_id(
            recurso_real,
            "partida",
        ),
        "recurso_id": _related_id(
            recurso_real,
            "recurso",
        ),
        "empleado_id": _related_id(
            recurso_real,
            "empleado",
        ),
        "movimiento_almacen_id": (
            _related_id(
                recurso_real,
                "movimiento_almacen",
            )
        ),
        "obra_id": getattr(
            obra,
            "pk",
            None,
        ),
        "obra_repr": (
            str(obra)
            if obra is not None
            else None
        ),
        "tarea_obra_repr": (
            _repr_relation(
                recurso_real,
                "tarea_obra",
            )
        ),
        "unidad_obra_repr": (
            _repr_relation(
                recurso_real,
                "unidad_obra",
            )
        ),
        "partida_repr": (
            _repr_relation(
                recurso_real,
                "partida",
            )
        ),
        "recurso_repr": (
            _repr_relation(
                recurso_real,
                "recurso",
            )
        ),
        "empleado_repr": (
            _repr_relation(
                recurso_real,
                "empleado",
            )
        ),
        "legacy_id_recurso_tarea": (
            getattr(
                recurso_real,
                "legacy_id_recurso_tarea",
                None,
            )
        ),
        "legacy_cod_obra": getattr(
            recurso_real,
            "legacy_cod_obra",
            None,
        ),
        "legacy_cod_fase": getattr(
            recurso_real,
            "legacy_cod_fase",
            None,
        ),
        "legacy_cod_vivienda": (
            getattr(
                recurso_real,
                "legacy_cod_vivienda",
                "",
            )
        ),
        "legacy_planta": getattr(
            recurso_real,
            "legacy_planta",
            "",
        ),
        "legacy_capitulo": getattr(
            recurso_real,
            "legacy_capitulo",
            "",
        ),
        "legacy_partida": getattr(
            recurso_real,
            "legacy_partida",
            "",
        ),
        "legacy_id_recurso": (
            getattr(
                recurso_real,
                "legacy_id_recurso",
                None,
            )
        ),
        "legacy_tipo_recurso": (
            getattr(
                recurso_real,
                "legacy_tipo_recurso",
                "",
            )
        ),
        "legacy_personal": getattr(
            recurso_real,
            "legacy_personal",
            None,
        ),
        "unidad": getattr(
            recurso_real,
            "unidad",
            "",
        ),
        "cantidad": getattr(
            recurso_real,
            "cantidad",
            None,
        ),
        "precio_unidad": getattr(
            recurso_real,
            "precio_unidad",
            None,
        ),
        "dias": getattr(
            recurso_real,
            "dias",
            None,
        ),
        "dias_reales": getattr(
            recurso_real,
            "dias_reales",
            None,
        ),
        "horas": getattr(
            recurso_real,
            "horas",
            None,
        ),
        "horas_reales": getattr(
            recurso_real,
            "horas_reales",
            None,
        ),
        "inicio_recurso_real": (
            getattr(
                recurso_real,
                "inicio_recurso_real",
                None,
            )
        ),
        "fin_recurso_real": (
            getattr(
                recurso_real,
                "fin_recurso_real",
                None,
            )
        ),
        "costo_recurso": getattr(
            recurso_real,
            "costo_recurso",
            None,
        ),
        "costo_recurso_real": (
            getattr(
                recurso_real,
                "costo_recurso_real",
                None,
            )
        ),
        "id_proveedor": getattr(
            recurso_real,
            "id_proveedor",
            "",
        ),
        "cod_albaran": getattr(
            recurso_real,
            "cod_albaran",
            "",
        ),
        "num_linea_albaran": (
            getattr(
                recurso_real,
                "num_linea_albaran",
                None,
            )
        ),
        "cod_factura": getattr(
            recurso_real,
            "cod_factura",
            "",
        ),
        "num_linea_factura": (
            getattr(
                recurso_real,
                "num_linea_factura",
                None,
            )
        ),
        "observaciones": getattr(
            recurso_real,
            "observaciones",
            "",
        ),
        "origen": raw.get(
            "origen"
        ),
        "creado_desde": raw.get(
            "creado_desde"
        ),
        "source": raw.get(
            "source"
        ),
        "created_by_user_id": raw.get(
            "created_by_user_id"
        ),
        "updated_by_user_id": raw.get(
            "updated_by_user_id"
        ),
        "raw_data": raw,
    }

    return _valor_json(
        snapshot
    )


def es_recurso_real_manual(
    value: Any,
) -> bool:
    snapshot = snapshot_recurso_real(
        value
    )

    source = str(
        snapshot.get("source")
        or ""
    )

    if source == SOURCE_ASIGNACION:
        return False

    if source.startswith(
        SOURCE_GESTION_PREFIX
    ):
        return False

    return (
        snapshot.get("origen")
        == ORIGEN_MANUAL
        and snapshot.get(
            "creado_desde"
        )
        == CREADO_DESDE_MANUAL
    )


def _resolver_team(
    value: Any,
    snapshot: dict,
):
    if not isinstance(value, dict):
        team = getattr(
            value,
            "team",
            None,
        )

        if team is not None:
            return team

    team_id = snapshot.get(
        "team_id"
    )

    if not team_id:
        return None

    Team = apps.get_model(
        "usuarios",
        "Team",
    )

    return (
        Team.objects
        .filter(pk=team_id)
        .first()
    )


def _url_recurso(
    snapshot: dict,
) -> str:
    tarea_id = snapshot.get(
        "tarea_obra_id"
    )

    if not tarea_id:
        return ""

    try:
        return reverse(
            (
                "planificacion_obra:"
                "planning_tarea_detail"
            ),
            args=[
                tarea_id,
            ],
        )

    except NoReverseMatch:
        return ""


def _objeto_repr(
    snapshot: dict,
) -> str:
    subject = (
        snapshot.get("empleado_repr")
        or snapshot.get("recurso_repr")
        or "Recurso real manual"
    )

    return (
        f"{subject} · "
        f"{snapshot.get('cantidad') or 0} "
        f"{snapshot.get('unidad') or ''}"
    ).strip()


def _suma_decimal(
    snapshots: Iterable[dict],
    field_name: str,
) -> str:
    total = Decimal("0")

    for snapshot in snapshots:
        value = snapshot.get(
            field_name
        )

        if value in {
            None,
            "",
        }:
            continue

        try:
            total += Decimal(
                str(value)
            )

        except Exception:
            continue

    return format(total, "f")


def _registrar(
    *,
    team,
    actor,
    accion: str,
    objeto_id: int,
    objeto_repr: str,
    descripcion: str,
    url: str,
    metadata: dict,
    agrupacion_key: str,
    clave_idempotencia: str,
):
    if team is None:
        raise ValueError(
            "No se pudo resolver el equipo "
            "del recurso real."
        )

    return registrar_actividad(
        modulo=MODULO,
        accion=accion,
        actor=actor,
        team=team,
        objeto=None,
        tipo_objeto=(
            "TareaRecursoReal"
        ),
        objeto_id=objeto_id,
        objeto_repr=objeto_repr,
        descripcion=descripcion,
        url=url,
        visibilidad=VISIBILIDAD,
        origen=ORIGEN_ACTIVIDAD,
        metadata=_valor_json(
            metadata
        ),
        agrupacion_key=(
            agrupacion_key
        ),
        clave_idempotencia=(
            clave_idempotencia
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=True,
    )


def registrar_creacion_recursos_reales_manuales(
    *,
    recursos_reales: Iterable[Any],
    actor,
    operation_id: str,
    fuente: str = (
        "tarea_recurso_real_create"
    ),
):
    recursos = list(
        recursos_reales
    )

    if not recursos:
        return None

    pairs = [
        (
            item,
            snapshot_recurso_real(
                item
            ),
        )
        for item in recursos
    ]

    if not all(
        es_recurso_real_manual(
            snapshot
        )
        for _, snapshot in pairs
    ):
        return None

    pairs.sort(
        key=lambda pair: (
            pair[1].get("id")
            or 0
        )
    )

    recursos = [
        item
        for item, _ in pairs
    ]

    snapshots = [
        snapshot
        for _, snapshot in pairs
    ]

    team_ids = {
        snapshot.get("team_id")
        for snapshot in snapshots
    }

    if len(team_ids) != 1:
        raise ValueError(
            "Una creación agrupada no "
            "puede mezclar equipos."
        )

    first_object = recursos[0]
    first = snapshots[0]

    team = _resolver_team(
        first_object,
        first,
    )

    resource_ids = [
        snapshot["id"]
        for snapshot in snapshots
    ]

    count = len(snapshots)

    metadata = {
        "operation_id": operation_id,
        "fuente": fuente,
        "cantidad_registros": count,
        "recurso_real_ids": (
            resource_ids
        ),
        "tarea_obra_ids": sorted({
            snapshot.get(
                "tarea_obra_id"
            )
            for snapshot in snapshots
            if snapshot.get(
                "tarea_obra_id"
            )
        }),
        "unidad_obra_ids": sorted({
            snapshot.get(
                "unidad_obra_id"
            )
            for snapshot in snapshots
            if snapshot.get(
                "unidad_obra_id"
            )
        }),
        "partida_ids": sorted({
            snapshot.get(
                "partida_id"
            )
            for snapshot in snapshots
            if snapshot.get(
                "partida_id"
            )
        }),
        "cantidad_total": (
            _suma_decimal(
                snapshots,
                "cantidad",
            )
        ),
        "coste_real_total": (
            _suma_decimal(
                snapshots,
                "costo_recurso_real",
            )
        ),
        "origen": ORIGEN_MANUAL,
        "creado_desde": (
            CREADO_DESDE_MANUAL
        ),
        "recursos": snapshots,
        "suprimir_actividad_derivada": (
            True
        ),
    }

    descripcion = (
        "Se registró un recurso real "
        "manual."
        if count == 1
        else (
            f"Se registraron {count} "
            "recursos reales manuales "
            "en una sola operación."
        )
    )

    return _registrar(
        team=team,
        actor=actor,
        accion=(
            "crear_recurso_real_manual"
        ),
        objeto_id=first["id"],
        objeto_repr=_objeto_repr(
            first
        ),
        descripcion=descripcion,
        url=_url_recurso(first),
        metadata=metadata,
        agrupacion_key=(
            "recurso_real_manual:"
            f"crear:{operation_id}"
        ),
        clave_idempotencia=(
            "planificacion_obra:"
            "recurso_real_manual:"
            f"crear:{operation_id}"
        ),
    )


def _cambios(
    anterior: dict,
    actual: dict,
) -> dict:
    result = {}

    for field_name in (
        CAMPOS_FUNCIONALES
    ):
        old_value = anterior.get(
            field_name
        )

        new_value = actual.get(
            field_name
        )

        if old_value != new_value:
            result[field_name] = {
                "anterior": old_value,
                "nuevo": new_value,
            }

    return result


def _categoria_cambio(
    fields: set[str],
) -> str:
    if fields & CAMPOS_DESTINO:
        return "REUBICACION_DESTINO"

    if fields & CAMPOS_RECURSO_PERSONA:
        return "RECURSO_O_EMPLEADO"

    if fields & CAMPOS_CANTIDAD_COSTE:
        return "CANTIDAD_HORAS_COSTE"

    if fields & CAMPOS_FECHA:
        return "FECHAS"

    if "observaciones" in fields:
        return "OBSERVACIONES"

    return "EDICION"


def registrar_cambio_recurso_real_manual(
    *,
    recurso_real: Any,
    actor,
    anterior: dict,
    operation_id: str,
    fuente: str = (
        "tarea_recurso_real_update"
    ),
):
    previous = snapshot_recurso_real(
        anterior
    )

    current = snapshot_recurso_real(
        recurso_real
    )

    if not (
        es_recurso_real_manual(
            previous
        )
        and es_recurso_real_manual(
            current
        )
    ):
        return None

    changes = _cambios(
        previous,
        current,
    )

    if not changes:
        return None

    fields = set(changes)

    category = _categoria_cambio(
        fields
    )

    descriptions = {
        "REUBICACION_DESTINO": (
            "Se cambió el destino de "
            "un recurso real manual."
        ),
        "RECURSO_O_EMPLEADO": (
            "Se cambió el recurso o "
            "empleado de una imputación "
            "real manual."
        ),
        "CANTIDAD_HORAS_COSTE": (
            "Se actualizaron cantidades, "
            "horas o costes de un recurso "
            "real manual."
        ),
        "FECHAS": (
            "Se actualizaron las fechas "
            "de un recurso real manual."
        ),
        "OBSERVACIONES": (
            "Se actualizaron las "
            "observaciones de un recurso "
            "real manual."
        ),
        "EDICION": (
            "Se actualizó un recurso "
            "real manual."
        ),
    }

    metadata = {
        "operation_id": operation_id,
        "fuente": fuente,
        "recurso_real_id": (
            current["id"]
        ),
        "categoria_cambio": category,
        "campos_cambiados": sorted(
            fields
        ),
        "cambios": changes,
        "anterior": previous,
        "actual": current,
        "origen": ORIGEN_MANUAL,
        "creado_desde": (
            CREADO_DESDE_MANUAL
        ),
        "suprimir_actividad_derivada": (
            True
        ),
    }

    return _registrar(
        team=_resolver_team(
            recurso_real,
            current,
        ),
        actor=actor,
        accion=(
            "editar_recurso_real_manual"
        ),
        objeto_id=current["id"],
        objeto_repr=_objeto_repr(
            current
        ),
        descripcion=descriptions[
            category
        ],
        url=_url_recurso(current),
        metadata=metadata,
        agrupacion_key=(
            "recurso_real_manual:"
            f"editar:{current['id']}"
        ),
        clave_idempotencia=(
            "planificacion_obra:"
            "recurso_real_manual:"
            f"editar:{operation_id}"
        ),
    )


def registrar_eliminacion_recurso_real_manual(
    *,
    recurso_real: Any,
    actor,
    anterior: dict,
    operation_id: str,
    fuente: str = (
        "tarea_recurso_real_delete"
    ),
):
    previous = snapshot_recurso_real(
        anterior
    )

    if not es_recurso_real_manual(
        previous
    ):
        return None

    object_id = previous.get("id")

    if not object_id:
        return None

    metadata = {
        "operation_id": operation_id,
        "fuente": fuente,
        "recurso_real_id": object_id,
        "tarea_obra_id": previous.get(
            "tarea_obra_id"
        ),
        "unidad_obra_id": previous.get(
            "unidad_obra_id"
        ),
        "partida_id": previous.get(
            "partida_id"
        ),
        "recurso_id": previous.get(
            "recurso_id"
        ),
        "empleado_id": previous.get(
            "empleado_id"
        ),
        "movimiento_almacen_id": (
            previous.get(
                "movimiento_almacen_id"
            )
        ),
        "anterior": previous,
        "origen": ORIGEN_MANUAL,
        "creado_desde": (
            CREADO_DESDE_MANUAL
        ),
        "suprimir_actividad_derivada": (
            True
        ),
    }

    return _registrar(
        team=_resolver_team(
            recurso_real,
            previous,
        ),
        actor=actor,
        accion=(
            "eliminar_recurso_real_manual"
        ),
        objeto_id=object_id,
        objeto_repr=_objeto_repr(
            previous
        ),
        descripcion=(
            "Se eliminó un recurso "
            "real manual."
        ),
        url=_url_recurso(previous),
        metadata=metadata,
        agrupacion_key=(
            "recurso_real_manual:"
            f"eliminar:{object_id}"
        ),
        clave_idempotencia=(
            "planificacion_obra:"
            "recurso_real_manual:"
            f"eliminar:{operation_id}"
        ),
    )


def registrar_reubicacion_recursos_reales_manuales(
    *,
    anteriores: Iterable[Any],
    posteriores: Iterable[Any],
    actor,
    operation_id: str,
    reason: str,
    result: dict | None = None,
    fuente: str = (
        "tarea_recurso_real_reubicar"
    ),
):
    previous_objects = list(
        anteriores
    )

    current_objects = list(
        posteriores
    )

    if not previous_objects:
        return None

    previous_pairs = [
        (
            item,
            snapshot_recurso_real(
                item
            ),
        )
        for item in previous_objects
    ]

    current_pairs = [
        (
            item,
            snapshot_recurso_real(
                item
            ),
        )
        for item in current_objects
    ]

    if not all(
        es_recurso_real_manual(
            snapshot
        )
        for _, snapshot in previous_pairs
    ):
        return None

    if current_pairs and not all(
        es_recurso_real_manual(
            snapshot
        )
        for _, snapshot in current_pairs
    ):
        return None

    previous_pairs.sort(
        key=lambda pair: (
            pair[1].get("id")
            or 0
        )
    )

    current_pairs.sort(
        key=lambda pair: (
            pair[1].get("id")
            or 0
        )
    )

    previous = [
        snapshot
        for _, snapshot in previous_pairs
    ]

    current = [
        snapshot
        for _, snapshot in current_pairs
    ]

    first_object = (
        previous_pairs[0][0]
    )

    first = previous[0]

    team_ids = {
        snapshot.get("team_id")
        for snapshot in previous
    }

    if len(team_ids) != 1:
        raise ValueError(
            "Una reubicación no puede "
            "mezclar equipos."
        )

    count = len(previous)

    metadata = {
        "operation_id": operation_id,
        "fuente": fuente,
        "motivo": reason,
        "cantidad_registros": count,
        "recurso_real_ids": [
            snapshot["id"]
            for snapshot in previous
        ],
        "recurso_real_ids_finales": [
            snapshot["id"]
            for snapshot in current
        ],
        "origen_tarea_ids": sorted({
            snapshot.get(
                "tarea_obra_id"
            )
            for snapshot in previous
            if snapshot.get(
                "tarea_obra_id"
            )
        }),
        "destino_tarea_ids": sorted({
            snapshot.get(
                "tarea_obra_id"
            )
            for snapshot in current
            if snapshot.get(
                "tarea_obra_id"
            )
        }),
        "anteriores": previous,
        "posteriores": current,
        "resultado": _valor_json(
            result or {}
        ),
        "origen": ORIGEN_MANUAL,
        "creado_desde": (
            CREADO_DESDE_MANUAL
        ),
        "suprimir_actividad_por_fila": (
            True
        ),
    }

    target = (
        current[0]
        if current
        else first
    )

    description = (
        "Se reubicó un recurso real "
        "manual."
        if count == 1
        else (
            f"Se reubicaron {count} "
            "recursos reales manuales "
            "en una sola operación."
        )
    )

    return _registrar(
        team=_resolver_team(
            first_object,
            first,
        ),
        actor=actor,
        accion=(
            "reubicar_recurso_real_manual"
        ),
        objeto_id=first["id"],
        objeto_repr=_objeto_repr(
            target
        ),
        descripcion=description,
        url=_url_recurso(target),
        metadata=metadata,
        agrupacion_key=(
            "recurso_real_manual:"
            f"reubicar:{operation_id}"
        ),
        clave_idempotencia=(
            "planificacion_obra:"
            "recurso_real_manual:"
            f"reubicar:{operation_id}"
        ),
    )
