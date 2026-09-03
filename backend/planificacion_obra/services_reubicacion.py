from decimal import Decimal
from uuid import uuid4

from django.apps import apps
from django.db import transaction
from django.utils import timezone


SCOPE_SINGLE = "single"
SCOPE_DOCUMENT_CURRENT_TASK = "document_current_task"

ALLOWED_SCOPES = {
    SCOPE_SINGLE,
    SCOPE_DOCUMENT_CURRENT_TASK,
}


class ReubicacionError(Exception):
    pass


def _decimal(value):
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _field_names(instance):
    return {
        field.name
        for field in instance._meta.concrete_fields
    }


def _set_if_exists(
    instance,
    field_name,
    value,
    update_fields,
):
    if field_name not in _field_names(instance):
        return

    setattr(instance, field_name, value)
    update_fields.add(field_name)


def _touch(instance, update_fields):
    fields = _field_names(instance)
    now = timezone.now()

    if "updated_at" in fields:
        instance.updated_at = now
        update_fields.add("updated_at")

    if "actualizado_en" in fields:
        instance.actualizado_en = now
        update_fields.add("actualizado_en")


def document_info(real):
    raw = dict(real.raw_data or {})

    origin = str(
        raw.get("origen_tipo")
        or (
            "FACTURA"
            if getattr(real, "cod_factura", "")
            else (
                "ALBARAN"
                if getattr(real, "cod_albaran", "")
                else ""
            )
        )
    ).strip().upper()

    document_id = raw.get("documento_id")

    line_id = (
        raw.get("linea_id")
        or raw.get("factura_linea_id")
        or raw.get("albaran_linea_id")
    )

    code = ""

    if origin == "FACTURA":
        code = str(
            getattr(real, "cod_factura", "")
            or ""
        ).strip()

    elif origin == "ALBARAN":
        code = str(
            getattr(real, "cod_albaran", "")
            or ""
        ).strip()

    return {
        "origin": origin,
        "document_id": document_id,
        "line_id": line_id,
        "code": code,
    }


def task_snapshot(task):
    unidad = task.unidad_obra
    obra = task.obra
    capitulo = task.capitulo
    partida = task.partida

    return {
        "task_id": task.id,
        "team_id": task.team_id,
        "obra_id": task.obra_id,
        "obra": str(obra) if obra else "",
        "legacy_cod_obra": (
            getattr(task, "legacy_cod_obra", None)
            or getattr(obra, "legacy_cod_obra", None)
        ),
        "unidad_obra_id": task.unidad_obra_id,
        "legacy_cod_fase": (
            getattr(task, "legacy_cod_fase", None)
            or getattr(unidad, "legacy_cod_fase", None)
        ),
        "legacy_cod_vivienda": (
            getattr(task, "legacy_cod_vivienda", None)
            or getattr(
                unidad,
                "legacy_cod_vivienda",
                None,
            )
            or getattr(unidad, "vivienda", None)
        ),
        "legacy_planta": (
            getattr(task, "legacy_planta", None)
            or ""
        ),
        "capitulo_id": task.capitulo_id,
        "capitulo_codigo": (
            getattr(capitulo, "codigo", "")
            if capitulo
            else ""
        ),
        "capitulo_nombre": (
            getattr(capitulo, "nombre", "")
            if capitulo
            else ""
        ),
        "partida_id": task.partida_id,
        "partida_codigo": (
            getattr(partida, "codigo", "")
            if partida
            else ""
        ),
        "partida_nombre": (
            getattr(partida, "nombre", "")
            if partida
            else ""
        ),
    }


def real_snapshot(real):
    return {
        "real_id": real.id,
        "recurso_id": real.recurso_id,
        "recurso": (
            str(real.recurso)
            if real.recurso_id
            else ""
        ),
        "cantidad": str(real.cantidad or 0),
        "unidad": str(real.unidad or ""),
        "precio_unidad": str(
            real.precio_unidad or 0
        ),
        "costo_recurso_real": str(
            real.costo_recurso_real or 0
        ),
        "fecha": (
            real.inicio_recurso_real.isoformat()
            if real.inicio_recurso_real
            else None
        ),
        "tarea_obra_id": real.tarea_obra_id,
        "unidad_obra_id": real.unidad_obra_id,
        "partida_id": real.partida_id,
        "legacy_cod_obra": getattr(
            real,
            "legacy_cod_obra",
            None,
        ),
        "legacy_cod_fase": getattr(
            real,
            "legacy_cod_fase",
            None,
        ),
        "legacy_cod_vivienda": getattr(
            real,
            "legacy_cod_vivienda",
            None,
        ),
        "legacy_planta": getattr(
            real,
            "legacy_planta",
            None,
        ),
        "movimiento_almacen_id": (
            real.movimiento_almacen_id
        ),
        "document": document_info(real),
    }


def _real_queryset(lock=False):
    Real = apps.get_model(
        "planificacion_obra",
        "TareaRecursoReal",
    )

    queryset = (
        Real.objects
        .select_related(
            "team",
            "recurso",
            "tarea_obra",
            "tarea_obra__obra",
            "tarea_obra__unidad_obra",
            "tarea_obra__capitulo",
            "tarea_obra__partida",
            "unidad_obra",
            "partida",
            "movimiento_almacen",
        )
    )

    if lock:
        queryset = queryset.select_for_update(
            of=("self",)
        )

    return queryset


def _task_queryset(lock=False):
    Tarea = apps.get_model(
        "planificacion_obra",
        "TareaObra",
    )

    queryset = (
        Tarea.objects
        .select_related(
            "team",
            "obra",
            "unidad_obra",
            "capitulo",
            "partida",
        )
    )

    if lock:
        queryset = queryset.select_for_update(
            of=("self",)
        )

    return queryset


def scope_queryset(real, scope, lock=False):
    if scope not in ALLOWED_SCOPES:
        raise ReubicacionError(
            "El alcance seleccionado no es válido."
        )

    queryset = _real_queryset(lock=lock)

    if scope == SCOPE_SINGLE:
        return queryset.filter(pk=real.pk)

    document = document_info(real)

    if (
        not document["origin"]
        or not document["document_id"]
    ):
        raise ReubicacionError(
            "La imputación no conserva un origen "
            "documental suficiente para agrupar líneas."
        )

    queryset = queryset.filter(
        team_id=real.team_id,
        tarea_obra_id=real.tarea_obra_id,
        recurso__isnull=False,
        raw_data__origen_tipo=document["origin"],
        raw_data__documento_id=document["document_id"],
    )

    if (
        document["origin"] == "FACTURA"
        and document["code"]
    ):
        queryset = queryset.filter(
            cod_factura=document["code"],
        )

    elif (
        document["origin"] == "ALBARAN"
        and document["code"]
    ):
        queryset = queryset.filter(
            cod_albaran=document["code"],
        )

    return queryset


def _validate_target(source_real, target_task):
    source_task = source_real.tarea_obra

    if not source_task:
        raise ReubicacionError(
            "La imputación no está vinculada a una tarea."
        )

    if not source_real.recurso_id:
        raise ReubicacionError(
            "Esta utilidad solo reubica recursos de obra, "
            "no asignaciones de personal."
        )

    if not source_task.obra_id:
        raise ReubicacionError(
            "La tarea de origen no tiene obra."
        )

    if not source_task.partida_id:
        raise ReubicacionError(
            "La tarea de origen no tiene partida."
        )

    if source_task.pk == target_task.pk:
        raise ReubicacionError(
            "La tarea de destino coincide con la actual."
        )

    if source_real.team_id != target_task.team_id:
        raise ReubicacionError(
            "No se puede reubicar entre equipos distintos."
        )

    if source_task.obra_id != target_task.obra_id:
        raise ReubicacionError(
            "No se puede cambiar de obra con esta utilidad."
        )

    if source_task.partida_id != target_task.partida_id:
        raise ReubicacionError(
            "La tarea de destino debe pertenecer "
            "a la misma partida."
        )

    if not target_task.unidad_obra_id:
        raise ReubicacionError(
            "La tarea de destino no tiene vivienda "
            "o unidad de obra."
        )


def preview_relocation(
    *,
    real_id,
    target_task_id,
    scope,
    lock=False,
):
    Real = apps.get_model(
        "planificacion_obra",
        "TareaRecursoReal",
    )

    source_real = _real_queryset(
        lock=lock,
    ).get(
        pk=real_id,
    )

    target_task = _task_queryset(
        lock=lock,
    ).get(
        pk=target_task_id,
    )

    _validate_target(
        source_real,
        target_task,
    )

    selected = list(
        scope_queryset(
            source_real,
            scope,
            lock=lock,
        ).order_by(
            "cod_factura",
            "num_linea_factura",
            "cod_albaran",
            "num_linea_albaran",
            "id",
        )
    )

    if not selected:
        raise ReubicacionError(
            "No se encontraron imputaciones "
            "para reubicar."
        )

    for item in selected:
        if not item.recurso_id:
            raise ReubicacionError(
                "El alcance contiene una asignación "
                "que no es un recurso de obra."
            )

        if (
            item.tarea_obra_id
            != source_real.tarea_obra_id
        ):
            raise ReubicacionError(
                "El alcance contiene destinos actuales "
                "diferentes."
            )

        if item.team_id != source_real.team_id:
            raise ReubicacionError(
                "El alcance contiene otro equipo."
            )

        item_document = document_info(item)
        source_document = document_info(source_real)

        if scope == SCOPE_DOCUMENT_CURRENT_TASK:
            if (
                item_document["origin"]
                != source_document["origin"]
                or item_document["document_id"]
                != source_document["document_id"]
            ):
                raise ReubicacionError(
                    "El alcance contiene documentos "
                    "diferentes."
                )

    selected_ids = {
        item.id
        for item in selected
    }

    movement_ids = {
        item.movimiento_almacen_id
        for item in selected
        if item.movimiento_almacen_id
    }

    for movement_id in movement_ids:
        linked_queryset = Real.objects.filter(
            movimiento_almacen_id=movement_id,
        )

        if lock:
            linked_queryset = (
                linked_queryset.select_for_update(
                    of=("self",)
                )
            )

        linked_ids = set(
            linked_queryset.values_list(
                "id",
                flat=True,
            )
        )

        missing_ids = linked_ids - selected_ids

        if missing_ids:
            raise ReubicacionError(
                "Un movimiento de almacén está vinculado "
                "a otras imputaciones no incluidas. "
                "Para evitar dividirlo faltan los recursos "
                f"{sorted(missing_ids)}."
            )

    total = Decimal("0")

    for item in selected:
        amount = item.costo_recurso_real

        if amount is None:
            amount = (
                _decimal(item.cantidad)
                * _decimal(item.precio_unidad)
            )

        total += _decimal(amount)

    return {
        "source_real": source_real,
        "source_task": source_real.tarea_obra,
        "target_task": target_task,
        "items": selected,
        "item_ids": sorted(selected_ids),
        "count": len(selected),
        "total": total,
        "movement_ids": sorted(movement_ids),
        "document": document_info(source_real),
        "source": task_snapshot(
            source_real.tarea_obra
        ),
        "target": task_snapshot(target_task),
    }


def _lock_document_lines(items):
    FacturaLinea = apps.get_model(
        "gestion",
        "FacturaProveedorLineaGestion",
    )
    AlbaranLinea = apps.get_model(
        "gestion",
        "AlbaranProveedorLineaGestion",
    )

    factura_refs = {}
    albaran_refs = {}

    for item in items:
        document = document_info(item)
        line_id = document.get("line_id")

        if not line_id:
            continue

        try:
            line_id = int(line_id)
        except Exception:
            raise ReubicacionError(
                "Una imputación contiene un identificador "
                "de línea documental no válido."
            )

        if document["origin"] == "FACTURA":
            factura_refs[line_id] = (
                document.get("document_id")
            )

        elif document["origin"] == "ALBARAN":
            albaran_refs[line_id] = (
                document.get("document_id")
            )

    locked = {}

    if factura_refs:
        rows = list(
            FacturaLinea.objects
            .select_for_update(of=("self",))
            .filter(id__in=factura_refs)
            .order_by("id")
        )

        if len(rows) != len(factura_refs):
            raise ReubicacionError(
                "No se encontraron todas las líneas "
                "de factura vinculadas."
            )

        for line in rows:
            expected = factura_refs[line.id]

            if (
                expected
                and line.factura_id != int(expected)
            ):
                raise ReubicacionError(
                    "Una línea de factura no pertenece "
                    "al documento indicado por la imputación."
                )

            locked[("FACTURA", line.id)] = line

    if albaran_refs:
        rows = list(
            AlbaranLinea.objects
            .select_for_update(of=("self",))
            .filter(id__in=albaran_refs)
            .order_by("id")
        )

        if len(rows) != len(albaran_refs):
            raise ReubicacionError(
                "No se encontraron todas las líneas "
                "de albarán vinculadas."
            )

        for line in rows:
            expected = albaran_refs[line.id]

            if (
                expected
                and line.albaran_id != int(expected)
            ):
                raise ReubicacionError(
                    "Una línea de albarán no pertenece "
                    "al documento indicado por la imputación."
                )

            locked[("ALBARAN", line.id)] = line

    return locked


def _update_real(
    real,
    target_task,
    *,
    operation_id,
    user,
    reason,
):
    before = real_snapshot(real)
    target = task_snapshot(target_task)
    update_fields = set()

    _set_if_exists(
        real,
        "tarea_obra",
        target_task,
        update_fields,
    )

    _set_if_exists(
        real,
        "unidad_obra",
        target_task.unidad_obra,
        update_fields,
    )

    _set_if_exists(
        real,
        "partida",
        target_task.partida,
        update_fields,
    )

    for field_name in (
        "legacy_cod_obra",
        "legacy_cod_fase",
        "legacy_cod_vivienda",
        "legacy_planta",
    ):
        _set_if_exists(
            real,
            field_name,
            target[field_name],
            update_fields,
        )

    event = {
        "operation_id": operation_id,
        "at": timezone.now().isoformat(),
        "user_id": getattr(user, "id", None),
        "username": getattr(user, "username", ""),
        "reason": reason,
        "before": before,
        "after": {
            "tarea_obra_id": target_task.id,
            "unidad_obra_id": (
                target_task.unidad_obra_id
            ),
            "partida_id": target_task.partida_id,
            "legacy_cod_obra": (
                target["legacy_cod_obra"]
            ),
            "legacy_cod_fase": (
                target["legacy_cod_fase"]
            ),
            "legacy_cod_vivienda": (
                target["legacy_cod_vivienda"]
            ),
            "legacy_planta": (
                target["legacy_planta"]
            ),
        },
    }

    raw = dict(real.raw_data or {})
    history = raw.get("reubicaciones", [])

    if not isinstance(history, list):
        history = []

    history.append(event)

    raw["reubicaciones"] = history
    raw["ultima_reubicacion"] = event
    raw["tarea_obra_id"] = target_task.id
    raw["unidad_obra_id"] = (
        target_task.unidad_obra_id
    )
    raw["partida_id"] = target_task.partida_id

    real.raw_data = raw
    update_fields.add("raw_data")

    _touch(real, update_fields)

    real.save(
        update_fields=sorted(update_fields),
    )

    return before


def _update_document_line(
    line,
    real,
    *,
    operation_id,
    user,
    reason,
    source,
    target,
):
    raw = dict(line.raw_data or {})

    history = raw.get(
        "reubicaciones_imputacion",
        [],
    )

    if not isinstance(history, list):
        history = []

    event = {
        "operation_id": operation_id,
        "at": timezone.now().isoformat(),
        "user_id": getattr(user, "id", None),
        "username": getattr(user, "username", ""),
        "reason": reason,
        "real_id": real.id,
        "source": source,
        "target": target,
    }

    history.append(event)

    raw["reubicaciones_imputacion"] = history
    raw["ultima_reubicacion_imputacion"] = event

    line.raw_data = raw

    update_fields = {"raw_data"}
    _touch(line, update_fields)

    line.save(
        update_fields=sorted(update_fields),
    )


def _update_movement(
    movement,
    target_task,
    *,
    operation_id,
    user,
    reason,
):
    target = task_snapshot(target_task)
    update_fields = set()

    before = {
        "movement_id": movement.id,
        "obra_id": movement.obra_id,
        "unidad_obra_id": movement.unidad_obra_id,
        "partida_id": movement.partida_id,
        "legacy_cod_obra": getattr(
            movement,
            "legacy_cod_obra",
            None,
        ),
        "legacy_cod_fase": getattr(
            movement,
            "legacy_cod_fase",
            None,
        ),
        "legacy_cod_vivienda": getattr(
            movement,
            "legacy_cod_vivienda",
            None,
        ),
        "legacy_planta": getattr(
            movement,
            "legacy_planta",
            None,
        ),
    }

    _set_if_exists(
        movement,
        "obra",
        target_task.obra,
        update_fields,
    )

    _set_if_exists(
        movement,
        "unidad_obra",
        target_task.unidad_obra,
        update_fields,
    )

    _set_if_exists(
        movement,
        "partida",
        target_task.partida,
        update_fields,
    )

    _set_if_exists(
        movement,
        "en_partida",
        True,
        update_fields,
    )

    for field_name in (
        "legacy_cod_obra",
        "legacy_cod_fase",
        "legacy_cod_vivienda",
        "legacy_planta",
    ):
        _set_if_exists(
            movement,
            field_name,
            target[field_name],
            update_fields,
        )

    event = {
        "operation_id": operation_id,
        "at": timezone.now().isoformat(),
        "user_id": getattr(user, "id", None),
        "username": getattr(user, "username", ""),
        "reason": reason,
        "before": before,
        "after": {
            "obra_id": target_task.obra_id,
            "unidad_obra_id": (
                target_task.unidad_obra_id
            ),
            "partida_id": target_task.partida_id,
            "legacy_cod_obra": (
                target["legacy_cod_obra"]
            ),
            "legacy_cod_fase": (
                target["legacy_cod_fase"]
            ),
            "legacy_cod_vivienda": (
                target["legacy_cod_vivienda"]
            ),
            "legacy_planta": (
                target["legacy_planta"]
            ),
        },
    }

    raw = dict(movement.raw_data or {})
    history = raw.get("reubicaciones", [])

    if not isinstance(history, list):
        history = []

    history.append(event)

    raw["reubicaciones"] = history
    raw["ultima_reubicacion"] = event

    movement.raw_data = raw
    update_fields.add("raw_data")

    _touch(movement, update_fields)

    movement.save(
        update_fields=sorted(update_fields),
    )

    return before


def _document_objects(document):
    Factura = apps.get_model(
        "gestion",
        "FacturaProveedorGestion",
    )
    Albaran = apps.get_model(
        "gestion",
        "AlbaranProveedorGestion",
    )

    factura = None
    albaran = None

    if document["origin"] == "FACTURA":
        if document["document_id"]:
            factura = Factura.objects.filter(
                pk=document["document_id"],
            ).first()

        if not factura and document["code"]:
            factura = Factura.objects.filter(
                cod_factura=document["code"],
            ).first()

    elif document["origin"] == "ALBARAN":
        if document["document_id"]:
            albaran = Albaran.objects.filter(
                pk=document["document_id"],
            ).first()

        if not albaran and document["code"]:
            albaran = Albaran.objects.filter(
                cod_albaran=document["code"],
            ).first()

    return factura, albaran


@transaction.atomic
def execute_relocation(
    *,
    real_id,
    target_task_id,
    scope,
    reason,
    user,
):
    reason = str(reason or "").strip()

    if len(reason) < 8:
        raise ReubicacionError(
            "El motivo debe explicar claramente "
            "la corrección."
        )

    plan = preview_relocation(
        real_id=real_id,
        target_task_id=target_task_id,
        scope=scope,
        lock=True,
    )

    operation_id = str(uuid4())

    Movimiento = apps.get_model(
        "planificacion_obra",
        "RecursoAlmacenMovimiento",
    )

    Audit = apps.get_model(
        "gestion",
        "GestionAuditLog",
    )

    movement_rows = list(
        Movimiento.objects
        .select_for_update(of=("self",))
        .filter(id__in=plan["movement_ids"])
        .order_by("id")
    )

    if len(movement_rows) != len(
        plan["movement_ids"]
    ):
        raise ReubicacionError(
            "No se encontraron todos los movimientos "
            "de almacén relacionados."
        )

    locked_lines = _lock_document_lines(
        plan["items"]
    )

    source = plan["source"]
    target = plan["target"]

    real_before = []

    for real in plan["items"]:
        real_before.append(
            _update_real(
                real,
                plan["target_task"],
                operation_id=operation_id,
                user=user,
                reason=reason,
            )
        )

        document = document_info(real)
        line_id = document.get("line_id")

        if line_id:
            key = (
                document["origin"],
                int(line_id),
            )

            line = locked_lines.get(key)

            if not line:
                raise ReubicacionError(
                    "No se encontró la línea documental "
                    "de una de las imputaciones."
                )

            _update_document_line(
                line,
                real,
                operation_id=operation_id,
                user=user,
                reason=reason,
                source=source,
                target=target,
            )

    movement_before = []

    for movement in movement_rows:
        movement_before.append(
            _update_movement(
                movement,
                plan["target_task"],
                operation_id=operation_id,
                user=user,
                reason=reason,
            )
        )

    factura, albaran = _document_objects(
        plan["document"]
    )

    document_label = (
        f'{plan["document"]["origin"]} '
        f'{plan["document"]["code"]}'
    ).strip()

    Audit.objects.create(
        team=plan["source_real"].team,
        usuario=user,
        accion="REUBICAR_IMPUTACION",
        entidad="TareaRecursoReal",
        objeto_id=plan["source_real"].id,
        objeto_repr=(
            f"{document_label or 'Imputación'} · "
            f"{plan['count']} línea(s)"
        )[:255],
        factura=factura,
        albaran=albaran,
        descripcion=(
            f"Reubicación de {plan['count']} "
            f"imputación(es): tarea "
            f"{source['task_id']} → "
            f"{target['task_id']}. "
            f"Motivo: {reason}"
        ),
        metadata={
            "operation_id": operation_id,
            "scope": scope,
            "reason": reason,
            "document": plan["document"],
            "real_ids": plan["item_ids"],
            "movement_ids": plan["movement_ids"],
            "amount": str(plan["total"]),
            "source": source,
            "target": target,
            "real_before": real_before,
            "movement_before": movement_before,
        },
    )

    return {
        "operation_id": operation_id,
        "count": plan["count"],
        "total": plan["total"],
        "real_ids": plan["item_ids"],
        "movement_ids": plan["movement_ids"],
        "document": plan["document"],
        "source": source,
        "target": target,
    }
