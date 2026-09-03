"""Reglas seguras para editar/eliminar movimientos manuales."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal

from django.db import transaction

from actividad.services import registrar_actividad
from planificacion_obra.models import RecursoAlmacenMovimiento, RecursoCatalogo, TareaRecursoReal


class StockRecalculationError(ValueError):
    pass


ORIGIN_LABELS = {
    "MANUAL": "Manual",
    "ALBARAN": "Desde albarán",
    "FACTURA": "Desde factura",
    "PARTIDA": "Vinculado a partida",
    "TAREA_REAL": "Vinculado a recurso real de planificación",
    "UNKNOWN": "Origen no identificado",
}


def _raw(mov):
    return mov.raw_data if isinstance(mov.raw_data, dict) else {}


def classify_movement(mov):
    if hasattr(mov, "tiene_real"):
        has_real = bool(mov.tiene_real)
    else:
        has_real = TareaRecursoReal.objects.filter(movimiento_almacen_id=mov.pk).exists()
    if has_real:
        return "TAREA_REAL"
    if mov.partida_id or mov.en_partida:
        return "PARTIDA"
    raw = _raw(mov)
    source = " ".join(str(raw.get(k) or "") for k in ("source", "origen", "created_from", "creado_desde")).lower()
    if mov.cod_albaran or any(token in source for token in ("albaran", "albarán")):
        return "ALBARAN"
    if mov.cod_factura or "factura" in source:
        return "FACTURA"
    manual_origins = {"obra_movil_almacen", "obra_movil_gasoil", "obra_movil_control_stock"}
    if raw.get("origen") in manual_origins or raw.get("source") in manual_origins:
        return "MANUAL"
    return "UNKNOWN"


def origin_label(origin):
    return ORIGIN_LABELS.get(origin, ORIGIN_LABELS["UNKNOWN"])


def permission_allowed(user, codename):
    return bool(user and user.is_authenticated and (user.is_superuser or user.has_perm(codename)))


def canonical_key(mov):
    created = mov.created_at.timestamp() if mov.created_at else float("-inf")
    return (
        mov.fecha_movimiento is not None,
        mov.fecha_movimiento or date.min,
        mov.hora_movimiento is not None,
        mov.hora_movimiento or time.min,
        created,
        mov.pk,
    )


def _delta(mov):
    quantity = Decimal(str(mov.cantidad or 0))
    if quantity < 0:
        quantity = abs(quantity)
    if mov.tipo_movimiento == "ENTRADA":
        return quantity
    if mov.tipo_movimiento in {"SALIDA", "ROTURA"}:
        return -quantity
    return Decimal("0")


def recalculate_resource_stock(resource_id):
    resource = RecursoCatalogo.objects.select_for_update().get(pk=resource_id)
    movements = list(
        RecursoAlmacenMovimiento.objects.select_for_update()
        .filter(recurso_id=resource_id)
        .order_by("fecha_movimiento", "hora_movimiento", "created_at", "pk")
    )
    groups = defaultdict(list)
    for movement in movements:
        groups[movement.almacen_id].append(movement)
    terminal_balances = []
    for rows in groups.values():
        rows.sort(key=canonical_key)
        first = rows[0]
        if first.tipo_movimiento == "CONTROL_STOCK":
            balance = Decimal("0")
        elif first.quedan is not None and first.cantidad is not None:
            balance = Decimal(str(first.quedan)) - _delta(first)
        else:
            raise StockRecalculationError("No se puede establecer con seguridad el saldo inicial del almacén.")
        for movement in rows:
            if movement.tipo_movimiento == "CONTROL_STOCK":
                balance = Decimal(str(movement.cantidad or 0))
            else:
                balance += _delta(movement)
            if balance < 0:
                raise StockRecalculationError("La operación produciría stock negativo; no se ha guardado ningún cambio.")
            new_quedan = balance.quantize(Decimal("0.0001"))
            if movement.quedan != new_quedan:
                movement.quedan = new_quedan
                movement.save(update_fields=["quedan", "updated_at"])
        terminal_balances.append(balance)
    total = sum(terminal_balances, Decimal("0")).quantize(Decimal("0.0000"))
    resource.stock = total
    resource.control_stock = True
    resource.save(update_fields=["stock", "control_stock", "actualizado_en"])
    return resource, total


def snapshot_movement(mov):
    return {
        "id": mov.pk,
        "legacy_id_movimiento": mov.legacy_id_movimiento,
        "team_id": mov.team_id,
        "almacen_id": mov.almacen_id,
        "recurso_id": mov.recurso_id,
        "tipo_movimiento": mov.tipo_movimiento,
        "cantidad": str(mov.cantidad) if mov.cantidad is not None else None,
        "quedan": str(mov.quedan) if mov.quedan is not None else None,
        "fecha_movimiento": mov.fecha_movimiento.isoformat() if mov.fecha_movimiento else None,
        "hora_movimiento": mov.hora_movimiento.isoformat() if mov.hora_movimiento else None,
        "observaciones": (mov.observaciones or "")[:500],
    }


def record_movement_activity(*, actor, movement, operation, before, after, stock_before, stock_after):
    registrar_actividad(
        modulo="obra_movil",
        accion=f"movimiento_almacen_{operation}",
        actor=actor,
        team=movement.team if movement is not None else None,
        objeto=movement,
        descripcion=f"Movimiento de almacén {operation}",
        metadata={
            "movement_id": before.get("id") if before else None,
            "before": before,
            "after": after,
            "resource_id": (after or before or {}).get("recurso_id"),
            "warehouse_id": (after or before or {}).get("almacen_id"),
            "stock_before": str(stock_before) if stock_before is not None else None,
            "stock_after": str(stock_after) if stock_after is not None else None,
            "result": "OK",
        },
        clave_idempotencia=f"movimiento_almacen:{operation}:{before.get('id') if before else after.get('id')}:{movement.updated_at.isoformat() if movement is not None and movement.updated_at else 'deleted'}",
    )


def _locked_movement(movement_id):
    # Bloquear solo la tabla base: varias FKs son nullable y PostgreSQL no
    # permite FOR UPDATE sobre el lado nullable de un outer join.
    locked = RecursoAlmacenMovimiento.objects.select_for_update().get(pk=movement_id)
    return RecursoAlmacenMovimiento.objects.select_related("team", "recurso", "almacen").get(pk=locked.pk)


@transaction.atomic
def update_manual_movement(*, movement_id, user, values):
    if not permission_allowed(user, "planificacion_obra.change_recursoalmacenmovimiento"):
        raise PermissionError("No tienes permiso para editar movimientos de almacén.")
    movement = _locked_movement(movement_id)
    if classify_movement(movement) != "MANUAL":
        raise PermissionError(f"No se puede editar: {origin_label(classify_movement(movement))}.")
    before = snapshot_movement(movement)
    resource = RecursoCatalogo.objects.select_for_update().get(pk=movement.recurso_id)
    stock_before = resource.stock
    movement.cantidad = values["cantidad"]
    movement.fecha_movimiento = values["fecha_movimiento"]
    movement.hora_movimiento = values["hora_movimiento"]
    movement.observaciones = values["observaciones"]
    movement.save(update_fields=["cantidad", "fecha_movimiento", "hora_movimiento", "observaciones", "updated_at"])
    resource, stock_after = recalculate_resource_stock(resource.pk)
    record_movement_activity(actor=user, movement=movement, operation="editado", before=before, after=snapshot_movement(movement), stock_before=stock_before, stock_after=stock_after)
    return movement, stock_after


@transaction.atomic
def delete_manual_movement(*, movement_id, user):
    if not permission_allowed(user, "planificacion_obra.delete_recursoalmacenmovimiento"):
        raise PermissionError("No tienes permiso para eliminar movimientos de almacén.")
    movement = _locked_movement(movement_id)
    if classify_movement(movement) != "MANUAL":
        raise PermissionError(f"No se puede eliminar: {origin_label(classify_movement(movement))}.")
    before = snapshot_movement(movement)
    resource = RecursoCatalogo.objects.select_for_update().get(pk=movement.recurso_id)
    stock_before = resource.stock
    movement.delete()
    resource, stock_after = recalculate_resource_stock(resource.pk)
    record_movement_activity(actor=user, movement=movement, operation="eliminado", before=before, after=None, stock_before=stock_before, stock_after=stock_after)
    return before, stock_after
