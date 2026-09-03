from __future__ import annotations

import uuid
from typing import Any

from django.utils import timezone

from actividad.services import (
    registrar_actividad,
)

from .models import Event


MODULE = "agenda"
AGENDA_URL = "/app/agenda/"


SNAPSHOT_FIELDS = (
    "title",
    "calendar_id",
    "start",
    "end",
    "all_day",
    "rrule",
    "rrule_until",
    "who_text",
    "who_user_ids",
    "description",
    "status",
    "location",
    "visibility",
    "obra_id",
    "obra_nombre",
)


TEMPORAL_FIELDS = {
    "start",
    "end",
    "all_day",
    "rrule",
    "rrule_until",
}


ATTENDEE_FIELDS = {
    "who_text",
    "who_user_ids",
}


SHARED_VISIBILITIES = {
    Event.Visibility.DEPARTAMENTO,
    Event.Visibility.GLOBAL,
}


def _serialize_value(value):
    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return value


def snapshot_evento(
    evento: Event,
) -> dict[str, Any]:
    """Captura estable del estado funcional del evento."""
    who_user_ids = []

    if evento.pk:
        who_user_ids = list(
            evento.who_users
            .order_by("pk")
            .values_list(
                "pk",
                flat=True,
            )
        )

    return {
        "id": evento.pk,
        "team_id": evento.team_id,
        "title": evento.title,
        "calendar_id": (
            evento.calendar_id
        ),
        "start": _serialize_value(
            evento.start
        ),
        "end": _serialize_value(
            evento.end
        ),
        "all_day": bool(
            evento.all_day
        ),
        "rrule": evento.rrule or "",
        "rrule_until": (
            _serialize_value(
                evento.rrule_until
            )
        ),
        "who_text": (
            evento.who_text or ""
        ),
        "who_user_ids": (
            who_user_ids
        ),
        "description": (
            evento.description or ""
        ),
        "status": evento.status,
        "location": (
            evento.location or ""
        ),
        "visibility": (
            evento.visibility
        ),
        "obra_id": evento.obra_id,
        "obra_nombre": (
            evento.obra_nombre or ""
        ),
        "created_by_id": (
            evento.created_by_id
        ),
        "updated_by_id": (
            evento.updated_by_id
        ),
        "created_at": (
            _serialize_value(
                evento.created_at
            )
        ),
        "updated_at": (
            _serialize_value(
                evento.updated_at
            )
        ),
    }


def _activity_visibility(
    snapshot: dict[str, Any],
) -> str:
    if (
        snapshot.get("team_id")
        and snapshot.get("visibility")
        in SHARED_VISIBILITIES
    ):
        return "EQUIPO"

    return "ACTOR"


def _human_datetime(value):
    if not value:
        return ""

    try:
        parsed = (
            timezone.datetime
            .fromisoformat(value)
        )

        if timezone.is_aware(parsed):
            parsed = timezone.localtime(
                parsed
            )

        return parsed.strftime(
            "%d/%m/%Y %H:%M"
        )

    except (
        TypeError,
        ValueError,
    ):
        return str(value)


def _status_label(value):
    return dict(
        Event.TaskStatus.choices
    ).get(
        value,
        value,
    )


def _changed_fields(
    anterior: dict[str, Any],
    actual: dict[str, Any],
) -> list[str]:
    return [
        field
        for field in SNAPSHOT_FIELDS
        if anterior.get(field)
        != actual.get(field)
    ]


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
        "status" in changed
        and actual.get("status")
        == Event.TaskStatus.COMPLETADO
    ):
        return "completar_evento"

    if changed & TEMPORAL_FIELDS:
        return "reprogramar_evento"

    if changed & ATTENDEE_FIELDS:
        return "cambiar_asistentes_evento"

    if "status" in changed:
        return "cambiar_estado_evento"

    return "editar_evento"


def _description_for_change(
    *,
    accion,
    actual,
):
    title = actual.get(
        "title"
    ) or "Sin título"

    if accion == "completar_evento":
        return (
            f"ha completado el evento "
            f"«{title}»."
        )

    if accion == "reprogramar_evento":
        return (
            f"ha reprogramado el evento "
            f"«{title}»."
        )

    if (
        accion
        == "cambiar_asistentes_evento"
    ):
        return (
            f"ha actualizado los asistentes "
            f"del evento «{title}»."
        )

    if accion == "cambiar_estado_evento":
        return (
            f"ha cambiado el estado del "
            f"evento «{title}» a "
            f"«{_status_label(actual.get('status'))}»."
        )

    return (
        f"ha actualizado el evento "
        f"«{title}»."
    )


def registrar_creacion_evento(
    *,
    evento,
    actor,
    fuente="formulario",
    diferir_hasta_commit=True,
):
    actual = snapshot_evento(
        evento
    )

    inicio = _human_datetime(
        actual.get("start")
    )

    descripcion = (
        f"ha creado el evento "
        f"«{evento.title}»"
    )

    if inicio:
        descripcion += (
            f" para el {inicio}"
        )

    descripcion += "."

    metadata = {
        "fuente": fuente,
        "evento_id": evento.pk,
        "team_id": evento.team_id,
        "titulo": evento.title,
        "calendar_id": (
            evento.calendar_id
        ),
        "visibilidad_evento": (
            evento.visibility
        ),
        "estado": evento.status,
        "inicio": actual["start"],
        "fin": actual["end"],
        "todo_el_dia": (
            actual["all_day"]
        ),
        "asistente_ids": (
            actual["who_user_ids"]
        ),
    }

    return registrar_actividad(
        team=evento.team,
        actor=actor,
        modulo=MODULE,
        accion="crear_evento",
        tipo_objeto=(
            evento._meta.label_lower
        ),
        objeto_id=evento.pk,
        objeto_repr=evento.title,
        descripcion=descripcion,
        url=AGENDA_URL,
        visibilidad=(
            _activity_visibility(actual)
        ),
        origen="EXPLICITO",
        metadata=metadata,
        agrupacion_key=(
            f"agenda:crear_evento:"
            f"{evento.pk}"
        ),
        clave_idempotencia=(
            f"agenda:crear:{evento.pk}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )


def registrar_cambio_evento(
    *,
    evento,
    actor,
    anterior,
    fuente="formulario",
    diferir_hasta_commit=True,
):
    actual = snapshot_evento(
        evento
    )

    campos_cambiados = (
        _changed_fields(
            anterior,
            actual,
        )
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

    metadata = {
        "fuente": fuente,
        "evento_id": evento.pk,
        "team_id": evento.team_id,
        "titulo": evento.title,
        "calendar_id": (
            evento.calendar_id
        ),
        "visibilidad_evento": (
            evento.visibility
        ),
        "estado_anterior": (
            anterior.get("status")
        ),
        "estado": actual.get(
            "status"
        ),
        "inicio_anterior": (
            anterior.get("start")
        ),
        "inicio": actual.get(
            "start"
        ),
        "fin_anterior": (
            anterior.get("end")
        ),
        "fin": actual.get("end"),
        "asistente_ids_anteriores": (
            anterior.get(
                "who_user_ids",
                [],
            )
        ),
        "asistente_ids": (
            actual.get(
                "who_user_ids",
                [],
            )
        ),
        "campos_cambiados": (
            campos_cambiados
        ),
        "valores_anteriores": {
            field: anterior.get(field)
            for field in campos_cambiados
        },
        "valores_actuales": {
            field: actual.get(field)
            for field in campos_cambiados
        },
    }

    revision = (
        actual.get("updated_at")
        or uuid.uuid4().hex
    )

    return registrar_actividad(
        team=evento.team,
        actor=actor,
        modulo=MODULE,
        accion=accion,
        tipo_objeto=(
            evento._meta.label_lower
        ),
        objeto_id=evento.pk,
        objeto_repr=evento.title,
        descripcion=(
            _description_for_change(
                accion=accion,
                actual=actual,
            )
        ),
        url=AGENDA_URL,
        visibilidad=(
            _activity_visibility(actual)
        ),
        origen="EXPLICITO",
        metadata=metadata,
        agrupacion_key=(
            f"agenda:{accion}:"
            f"{evento.pk}"
        ),
        clave_idempotencia=(
            f"agenda:{accion}:"
            f"{evento.pk}:{revision}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )


def registrar_eliminacion_evento(
    *,
    evento,
    actor,
    anterior=None,
    fuente="api",
    diferir_hasta_commit=True,
):
    anterior = (
        anterior
        or snapshot_evento(evento)
    )

    evento_id = anterior["id"]

    revision = (
        anterior.get("updated_at")
        or anterior.get("created_at")
        or uuid.uuid4().hex
    )

    return registrar_actividad(
        team=evento.team,
        actor=actor,
        modulo=MODULE,
        accion="eliminar_evento",
        tipo_objeto=(
            evento._meta.label_lower
        ),
        objeto_id=evento_id,
        objeto_repr=(
            anterior.get("title")
            or "Evento"
        ),
        descripcion=(
            "ha eliminado el evento "
            f"«{anterior.get('title') or 'Sin título'}»."
        ),
        url=AGENDA_URL,
        visibilidad=(
            _activity_visibility(
                anterior
            )
        ),
        origen="EXPLICITO",
        metadata={
            "fuente": fuente,
            "evento_id": evento_id,
            "team_id": (
                anterior.get("team_id")
            ),
            "titulo": (
                anterior.get("title")
            ),
            "calendar_id": (
                anterior.get(
                    "calendar_id"
                )
            ),
            "visibilidad_evento": (
                anterior.get(
                    "visibility"
                )
            ),
            "estado": (
                anterior.get("status")
            ),
            "inicio": (
                anterior.get("start")
            ),
            "fin": anterior.get("end"),
            "asistente_ids": (
                anterior.get(
                    "who_user_ids",
                    [],
                )
            ),
        },
        agrupacion_key=(
            f"agenda:eliminar_evento:"
            f"{evento_id}"
        ),
        clave_idempotencia=(
            f"agenda:eliminar:"
            f"{evento_id}:{revision}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )


def registrar_importacion_eventos(
    *,
    team,
    actor,
    evento_ids,
    titulos,
    omitidos=0,
    operation_id=None,
    diferir_hasta_commit=True,
):
    evento_ids = list(
        evento_ids or []
    )

    titulos = list(
        titulos or []
    )

    if not evento_ids:
        return None

    operation_id = (
        operation_id
        or uuid.uuid4().hex
    )

    cantidad = len(
        evento_ids
    )

    if cantidad == 1:
        descripcion = (
            "ha importado 1 evento "
            "en Agenda."
        )

        objeto_repr = (
            titulos[0]
            if titulos
            else "1 evento"
        )

        objeto_id = evento_ids[0]

    else:
        descripcion = (
            f"ha importado {cantidad} "
            f"eventos en Agenda."
        )

        objeto_repr = (
            f"{cantidad} eventos"
        )

        objeto_id = None

    metadata_truncada = (
        len(evento_ids) > 100
        or len(titulos) > 20
    )

    return registrar_actividad(
        team=team,
        actor=actor,
        modulo=MODULE,
        accion="importar_eventos",
        tipo_objeto=(
            "agenda.importacion"
        ),
        objeto_id=objeto_id,
        objeto_repr=objeto_repr,
        descripcion=descripcion,
        url=AGENDA_URL,
        visibilidad="EQUIPO",
        origen="EXPLICITO",
        metadata={
            "fuente": "csv",
            "operation_id": (
                operation_id
            ),
            "cantidad": cantidad,
            "omitidos": omitidos,
            "evento_ids": (
                evento_ids[:100]
            ),
            "titulos": titulos[:20],
            "metadata_truncada": (
                metadata_truncada
            ),
        },
        agrupacion_key=(
            "agenda:importar_eventos:"
            f"{operation_id}"
        ),
        clave_idempotencia=(
            "agenda:importar:"
            f"{operation_id}"
        ),
        visible_en_dashboard=True,
        diferir_hasta_commit=(
            diferir_hasta_commit
        ),
    )
