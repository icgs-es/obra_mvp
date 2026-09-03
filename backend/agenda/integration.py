"""Contrato compartido Agenda ↔ Tareas, sin mezclar sus modelos."""

from __future__ import annotations

import datetime as dt

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from tareas.access import editable_tasks_for_user, visible_tasks_for_user
from tareas.models import Tarea

from .access import editable_events_for_user, visible_events_for_user
from .models import Event
from .user_colors import (
    event_color_payload,
    event_identity_payload,
    owner_color_payload,
    owner_identity_payload,
)


def _visibility_values_for_tasks(event_visibility_values):
    mapping = {
        Event.Visibility.PRIVADA: "privada",
        Event.Visibility.DEPARTAMENTO: "depto",
        Event.Visibility.GLOBAL: "global",
    }
    return [mapping[value] for value in event_visibility_values if value in mapping]


def tasks_between_for_user(
    user,
    start,
    end,
    *,
    active_team_id="all",
    visibility_values=None,
):
    start_date = timezone.localtime(start).date()
    end_date = timezone.localtime(end).date()
    queryset = visible_tasks_for_user(
        user,
        active_team_id=active_team_id,
        queryset=Tarea.objects.all(),
    )

    if visibility_values:
        queryset = queryset.filter(
            visibilidad__in=_visibility_values_for_tasks(visibility_values)
        )

    queryset = queryset.filter(
        Q(
            inicio_programado__lt=end,
        )
        & (
            Q(fin_programado__gte=start)
            | Q(fin_programado__isnull=True)
        )
        | Q(
            inicio_programado__isnull=True,
            vencimiento__gte=start_date,
            vencimiento__lt=end_date,
        )
    )

    return queryset.select_related("team", "creador").prefetch_related("asignados")


def _state_presentation(*, completed=False, cancelled=False, overdue=False):
    if cancelled:
        return "cancelled", "⊘", "Cancelado"
    if completed:
        return "completed", "✓", "Completado"
    if overdue:
        return "overdue", "⚠", "Atrasado"
    return "normal", "", ""


def serialize_event(event, user_map, *, editable=False, now=None):
    now = now or timezone.now()
    overdue = event.is_overdue_at(now)
    visual_state, indicator, state_notice = _state_presentation(
        completed=event.is_completed,
        cancelled=event.is_cancelled,
        overdue=overdue,
    )
    return {
        "id": f"EVENTO:{event.pk}",
        "title": event.title,
        "start": event.start.isoformat(),
        "end": (event.end or event.start).isoformat(),
        "allDay": bool(event.all_day),
        "editable": bool(editable),
        "startEditable": bool(editable),
        "durationEditable": bool(editable),
        **event_color_payload(event, user_map),
        "extendedProps": {
            **event_identity_payload(event, user_map),
            "item_type": "EVENTO",
            "item_pk": event.pk,
            "type_label": "Evento",
            "location": event.location,
            "visibility": event.visibility,
            "status": event.status,
            "status_label": event.get_status_display(),
            "company": event.team.name if event.team_id else "Sin empresa · legacy",
            "company_id": event.team_id,
            "completed": event.is_completed,
            "cancelled": event.is_cancelled,
            "overdue": overdue,
            "visual_state": visual_state,
            "indicator": indicator,
            "state_notice": state_notice,
            "edit_url": reverse("agenda:edit", args=[event.pk]) if editable else None,
            "update_url": (
                reverse("agenda:api_event_detail", args=[event.pk]) if editable else None
            ),
            "action_url": (
                reverse("agenda:event_action", args=[event.pk]) if editable else None
            ),
            "can_edit": bool(editable),
            "recurring": bool(event.rrule),
        },
    }


def serialize_task(task, user_map, *, editable=False, now=None):
    now = now or timezone.now()
    overdue = task.is_overdue_at(now)
    visual_state, indicator, state_notice = _state_presentation(
        completed=task.is_completed,
        overdue=overdue,
    )
    scheduled = task.inicio_programado is not None
    if scheduled:
        start = task.inicio_programado.isoformat()
        end = (task.fin_programado or task.inicio_programado).isoformat()
        all_day = False
    else:
        start = task.vencimiento.isoformat()
        end = (task.vencimiento + dt.timedelta(days=1)).isoformat()
        all_day = True

    return {
        "id": f"TAREA:{task.pk}",
        "title": task.titulo,
        "start": start,
        "end": end,
        "allDay": all_day,
        "editable": bool(editable),
        "startEditable": bool(editable),
        "durationEditable": bool(editable and scheduled),
        **owner_color_payload(task.creador_id, user_map),
        "extendedProps": {
            **owner_identity_payload(task.creador_id, user_map),
            "item_type": "TAREA",
            "item_pk": task.pk,
            "type_label": "Tarea",
            "location": "",
            "visibility": task.visibilidad.upper(),
            "status": task.estado,
            "status_label": task.get_estado_display(),
            "priority": task.prioridad,
            "priority_label": task.get_prioridad_display(),
            "company": task.team.name if task.team_id else "Sin empresa · legacy",
            "company_id": task.team_id,
            "completed": task.is_completed,
            "cancelled": False,
            "overdue": overdue,
            "visual_state": visual_state,
            "indicator": indicator,
            "state_notice": state_notice,
            "edit_url": reverse("tareas:update", args=[task.pk]) if editable else None,
            "update_url": (
                reverse("tareas:api_detail", args=[task.pk]) if editable else None
            ),
            "action_url": (
                reverse("tareas:action", args=[task.pk]) if editable else None
            ),
            "can_edit": bool(editable),
            "scheduled": scheduled,
        },
    }


def unified_calendar_items(
    user,
    start,
    end,
    user_map,
    *,
    active_team_id="all",
    event_queryset=None,
    visibility_values=None,
):
    event_queryset = event_queryset if event_queryset is not None else Event.objects.all()
    events = visible_events_for_user(
        user,
        active_team_id=active_team_id,
        queryset=event_queryset,
    ).filter(start__lt=end).filter(Q(end__gte=start) | Q(end__isnull=True))
    events = events.select_related("calendar", "created_by", "team").prefetch_related(
        "who_users"
    )
    tasks = tasks_between_for_user(
        user,
        start,
        end,
        active_team_id=active_team_id,
        visibility_values=visibility_values,
    )

    editable_event_ids = set(
        editable_events_for_user(
            user, active_team_id=active_team_id, queryset=events
        ).values_list("pk", flat=True)
    )
    editable_task_ids = set(
        editable_tasks_for_user(
            user, active_team_id=active_team_id, queryset=tasks
        ).values_list("pk", flat=True)
    )
    now = timezone.now()
    items = [
        serialize_event(event, user_map, editable=event.pk in editable_event_ids, now=now)
        for event in events
    ]
    items.extend(
        serialize_task(task, user_map, editable=task.pk in editable_task_ids, now=now)
        for task in tasks
    )
    return items


def _deadline(item):
    if isinstance(item, Event):
        return item.end or item.start
    if item.fin_programado or item.inicio_programado:
        return item.fin_programado or item.inicio_programado
    return timezone.make_aware(dt.datetime.combine(item.vencimiento, dt.time.max))


def personal_agenda_payload(user, user_map, *, active_team_id="all", days=7):
    now = timezone.now()
    today = timezone.localdate(now)
    tomorrow = today + dt.timedelta(days=1)
    limit = today + dt.timedelta(days=days + 1)

    events = visible_events_for_user(
        user, active_team_id=active_team_id
    ).filter(Q(created_by=user) | Q(who_users=user)).select_related(
        "team", "created_by"
    ).prefetch_related("who_users").distinct()
    tasks = visible_tasks_for_user(
        user, active_team_id=active_team_id
    ).filter(Q(creador=user) | Q(asignados=user)).select_related(
        "team", "creador"
    ).prefetch_related("asignados").distinct()
    editable_event_ids = set(
        editable_events_for_user(
            user, active_team_id=active_team_id, queryset=events
        ).values_list("pk", flat=True)
    )
    editable_task_ids = set(
        editable_tasks_for_user(
            user, active_team_id=active_team_id, queryset=tasks
        ).values_list("pk", flat=True)
    )

    overdue = []
    current = []
    upcoming = []

    def place(model_item, payload, item_date):
        entry = {
            "id": payload["id"],
            "title": payload["title"],
            "start": payload["start"],
            "all_day": payload["allDay"],
            **payload["extendedProps"],
        }
        if model_item.is_overdue_at(now):
            overdue.append((_deadline(model_item), entry))
        elif item_date == today:
            current.append((_deadline(model_item), entry))
        elif tomorrow <= item_date < limit:
            upcoming.append((_deadline(model_item), entry))

    for event in events:
        event_date = timezone.localdate(event.start)
        place(
            event,
            serialize_event(
                event, user_map, editable=event.pk in editable_event_ids, now=now
            ),
            event_date,
        )
    for task in tasks:
        if task.inicio_programado:
            task_date = timezone.localdate(task.inicio_programado)
        elif task.vencimiento:
            task_date = task.vencimiento
        else:
            continue
        place(
            task,
            serialize_task(
                task, user_map, editable=task.pk in editable_task_ids, now=now
            ),
            task_date,
        )

    def ordered(values):
        return [entry for _, entry in sorted(values, key=lambda value: value[0])]

    return {
        "overdue": ordered(overdue),
        "today": ordered(current),
        "upcoming": ordered(upcoming),
        "counts": {
            "overdue": len(overdue),
            "today": len(current),
            "upcoming": len(upcoming),
        },
    }
