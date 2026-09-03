from collections.abc import Mapping
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from .models import ActividadPlataforma


def _normalizar_texto(value: Any, max_length: int) -> str:
    if value is None:
        return ""

    return str(value).strip()[:max_length]


def _datos_objeto(objeto):
    if objeto is None:
        return {
            "tipo_objeto": "",
            "objeto_id": None,
            "objeto_repr": "",
            "team": None,
        }

    meta = getattr(objeto, "_meta", None)

    tipo_objeto = (
        meta.label_lower
        if meta is not None
        else objeto.__class__.__name__
    )

    return {
        "tipo_objeto": tipo_objeto,
        "objeto_id": getattr(objeto, "pk", None),
        "objeto_repr": _normalizar_texto(objeto, 255),
        "team": getattr(objeto, "team", None),
    }


def registrar_actividad(
    *,
    modulo,
    accion,
    actor=None,
    team=None,
    objeto=None,
    tipo_objeto="",
    objeto_id=None,
    objeto_repr="",
    descripcion="",
    url="",
    visibilidad=ActividadPlataforma.Visibilidad.EQUIPO,
    origen=ActividadPlataforma.Origen.EXPLICITO,
    metadata=None,
    agrupacion_key="",
    clave_idempotencia=None,
    visible_en_dashboard=True,
    ocurrida_en=None,
    diferir_hasta_commit=True,
):
    """
    Registra una acción funcional relevante de INTASA Platform.

    No sustituye los logs técnicos ni la auditoría de cada módulo.

    Cuando se ejecuta dentro de una transacción, el registro se difiere
    hasta que la operación principal haya confirmado correctamente.
    """

    modulo = _normalizar_texto(modulo, 50)
    accion = _normalizar_texto(accion, 50)

    if not modulo:
        raise ValueError("modulo es obligatorio")

    if not accion:
        raise ValueError("accion es obligatoria")

    datos_objeto = _datos_objeto(objeto)

    if team is None:
        team = datos_objeto["team"]

    tipo_objeto = _normalizar_texto(
        tipo_objeto or datos_objeto["tipo_objeto"],
        100,
    )

    if objeto_id is None:
        objeto_id = datos_objeto["objeto_id"]

    objeto_repr = _normalizar_texto(
        objeto_repr or datos_objeto["objeto_repr"],
        255,
    )

    if metadata is None:
        metadata = {}
    elif not isinstance(metadata, Mapping):
        raise TypeError("metadata debe ser un diccionario")
    else:
        metadata = dict(metadata)

    clave_idempotencia = (
        _normalizar_texto(clave_idempotencia, 255)
        or None
    )

    payload = {
        "team": team,
        "actor": actor,
        "modulo": modulo,
        "accion": accion,
        "tipo_objeto": tipo_objeto,
        "objeto_id": objeto_id,
        "objeto_repr": objeto_repr,
        "descripcion": str(descripcion or "").strip(),
        "url": _normalizar_texto(url, 500),
        "visibilidad": visibilidad,
        "origen": origen,
        "metadata": metadata,
        "agrupacion_key": _normalizar_texto(
            agrupacion_key,
            255,
        ),
        "clave_idempotencia": clave_idempotencia,
        "visible_en_dashboard": bool(visible_en_dashboard),
        "ocurrida_en": ocurrida_en or timezone.now(),
    }

    def crear_registro():
        if clave_idempotencia:
            actividad, _created = (
                ActividadPlataforma.objects.get_or_create(
                    clave_idempotencia=clave_idempotencia,
                    defaults=payload,
                )
            )
            return actividad

        return ActividadPlataforma.objects.create(**payload)

    if diferir_hasta_commit and connection.in_atomic_block:
        transaction.on_commit(crear_registro)
        return None

    return crear_registro()
