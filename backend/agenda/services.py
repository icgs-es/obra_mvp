# backend/agenda/services.py
from __future__ import annotations

from django.db import models

ADMIN_GROUPS = {"Administrador", "Gerencia"}


def user_is_admin_like(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    names = set(user.groups.values_list("name", flat=True))
    return bool(ADMIN_GROUPS & names)


def user_can_see_event(user, ev) -> bool:
    """
    Reglas de visibilidad (alineadas con models.Event):
    - Admin/Gerencia/superuser: todo.
    - visibility == GLOBAL: todos.
    - visibility == PRIVADA: created_by o invitado (who_users).
    - visibility == DEPARTAMENTO: (si hay calendar.departamento) o invitado (fallback).
    """
    if user_is_admin_like(user):
        return True

    vis = (getattr(ev, "visibility", None) or "PRIVADA").upper()

    if vis == "GLOBAL":
        return True

    # PRIVADA
    if vis == "PRIVADA":
        creator = getattr(ev, "created_by", None)
        if creator and getattr(creator, "id", None) == user.id:
            return True
        return ev.who_users.filter(id=user.id).exists()

    # DEPARTAMENTO
    if vis == "DEPARTAMENTO":
        cal = getattr(ev, "calendar", None)
        dep = getattr(cal, "departamento", None) if cal else None
        if dep is not None:
            # Si tu modelo de departamento/equipo tiene members/leads, lo aprovechamos.
            try:
                if user in dep.members.all() or user in dep.leads.all():
                    return True
            except Exception:
                pass
        # Fallback: si está invitado, también ve
        return ev.who_users.filter(id=user.id).exists()

    return False


def events_between_for_user(user, start, end, base_qs):
    """
    Ventana [start, end) + filtro por reglas de user_can_see_event.
    Compatible con FullCalendar.
    """
    qs = base_qs.filter(start__lt=end).filter(
        models.Q(end__gte=start) | models.Q(end__isnull=True)
    )
    return [e for e in qs.select_related("calendar", "created_by") if user_can_see_event(user, e)]

