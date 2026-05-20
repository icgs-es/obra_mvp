from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import AsignacionObra, EmpleadoObra, TareaRecursoReal


PORTAL_LEGACY_RECURSO_TAREA_OFFSET = 300000


class RealizacionAsignacionError(Exception):
    pass


def legacy_id_recurso_tarea_for_asignacion(asignacion: AsignacionObra) -> int:
    return PORTAL_LEGACY_RECURSO_TAREA_OFFSET + int(asignacion.pk)


def calcular_horas_asignacion(asignacion: AsignacionObra) -> Decimal:
    inicio = datetime.combine(asignacion.fecha_inicio, asignacion.hora_inicio)
    fin = datetime.combine(asignacion.fecha_fin, asignacion.hora_fin)

    if fin <= inicio:
        raise RealizacionAsignacionError("La fecha/hora fin debe ser posterior a la fecha/hora inicio.")

    seconds = Decimal(str((fin - inicio).total_seconds()))
    return (seconds / Decimal("3600")).quantize(Decimal("0.0001"))


def buscar_empleado_obra(asignacion: AsignacionObra) -> EmpleadoObra:
    empleado_obra = (
        EmpleadoObra.objects
        .filter(
            team=asignacion.team,
            rrhh_empleado=asignacion.empleado,
        )
        .order_by("-id")
        .first()
    )

    if not empleado_obra:
        raise RealizacionAsignacionError(
            f"No existe EmpleadoObra vinculado al empleado RRHH #{asignacion.empleado_id}."
        )

    return empleado_obra


def _codigo(obj, default=""):
    if not obj:
        return default
    return (
        getattr(obj, "codigo", None)
        or getattr(obj, "cod_partida", None)
        or getattr(obj, "cod_capitulo", None)
        or getattr(obj, "nombre", None)
        or default
    )


def _tipo_recurso_empleado(empleado_obra: EmpleadoObra) -> str:
    raw = empleado_obra.raw_data or {}
    tipo = raw.get("Tipo") or raw.get("tipo")
    if tipo:
        return str(tipo).strip()

    if empleado_obra.tipo == "ADMINISTRADA":
        return "M.O. ADM."

    return "M.O. CONT."


def _precio_hora(asignacion: AsignacionObra, empleado_obra: EmpleadoObra) -> Decimal:
    precio = empleado_obra.precio_hora
    if precio is None:
        precio = getattr(asignacion.empleado, "coste_hora", None)
    if precio is None:
        precio = Decimal("0.0000")
    return Decimal(precio).quantize(Decimal("0.0001"))


@transaction.atomic
def realizar_asignacion_obra(asignacion: AsignacionObra, user=None) -> TareaRecursoReal:
    """
    Convierte una AsignacionObra planificada en recurso real de tarea.

    Regla:
    - La AsignacionObra se conserva como trazabilidad.
    - Se crea/actualiza TareaRecursoReal con legacy_id_recurso_tarea = 300000 + asignacion.id.
    - La asignación pasa a estado REALIZADO.
    """

    if not asignacion.pk:
        raise RealizacionAsignacionError("La asignación debe estar guardada antes de realizarla.")

    today = timezone.localdate()
    if asignacion.fecha_inicio > today or asignacion.fecha_fin > today:
        raise RealizacionAsignacionError(
            "No se puede marcar como realizada una asignación con fecha futura. "
            "Ajusta primero la fecha real de ejecución."
        )

    if asignacion.estado == AsignacionObra.Estado.REALIZADO:
        # Es idempotente: si ya está realizada, devolvemos/actualizamos su real asociado.
        pass

    empleado_obra = buscar_empleado_obra(asignacion)
    tarea = asignacion.tarea_obra
    unidad_obra = asignacion.unidad_obra or getattr(tarea, "unidad_obra", None)
    partida = asignacion.partida or getattr(tarea, "partida", None)
    capitulo = asignacion.capitulo or getattr(tarea, "capitulo", None)

    horas = calcular_horas_asignacion(asignacion)
    dias_reales = Decimal(str((asignacion.fecha_fin - asignacion.fecha_inicio).days + 1)).quantize(Decimal("0.0001"))
    precio = _precio_hora(asignacion, empleado_obra)
    coste_real = (horas * precio).quantize(Decimal("0.0001"))

    legacy_id = legacy_id_recurso_tarea_for_asignacion(asignacion)

    raw_data = {
        "source": "portal_asignacion_obra",
        "asignacion_obra_id": asignacion.id,
        "created_by_user_id": getattr(user, "id", None),
        "legacy_id_policy": "300000 + asignacion_obra.id",
    }

    defaults = {
        "tarea_obra": tarea,
        "unidad_obra": unidad_obra,
        "partida": partida,
        "empleado": empleado_obra,
        "legacy_cod_obra": getattr(tarea, "legacy_cod_obra", None),
        "legacy_cod_fase": getattr(tarea, "legacy_cod_fase", None),
        "legacy_cod_vivienda": getattr(tarea, "legacy_cod_vivienda", "") or "",
        "legacy_planta": getattr(tarea, "legacy_planta", "") or "",
        "legacy_capitulo": getattr(tarea, "legacy_capitulo", "") or _codigo(capitulo),
        "legacy_partida": getattr(tarea, "legacy_partida", "") or _codigo(partida),
        "legacy_id_recurso": empleado_obra.legacy_id,
        "legacy_tipo_recurso": _tipo_recurso_empleado(empleado_obra),
        "legacy_personal": 0,
        "legacy_orden_recurso": None,
        "unidad": "HRS",
        "cantidad": horas,
        "precio_unidad": precio,
        "dias": Decimal("0.0000"),
        "dias_reales": dias_reales,
        "horas": Decimal("0.0000"),
        "horas_reales": horas,
        "inicio_recurso_real": asignacion.fecha_inicio,
        "fin_recurso_real": asignacion.fecha_fin,
        "costo_recurso": Decimal("0.0000"),
        "costo_recurso_real": coste_real,
        "control_suministros": False,
        "avisar": 0,
        "observaciones": asignacion.observaciones or f"Realizado desde asignación #{asignacion.id}",
        "raw_data": raw_data,
    }

    recurso_real, _created = TareaRecursoReal.objects.update_or_create(
        team=asignacion.team,
        legacy_id_recurso_tarea=legacy_id,
        defaults=defaults,
    )

    if asignacion.estado != AsignacionObra.Estado.REALIZADO:
        asignacion.estado = AsignacionObra.Estado.REALIZADO
        asignacion.save(update_fields=["estado", "actualizado_en"])

    return recurso_real
