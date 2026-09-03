from __future__ import annotations

from django.db import models

from .access import (
    user_can_view_event,
    user_is_agenda_manager,
    visible_events_for_user,
)


def user_is_admin_like(user):
    """Alias compatible con el código histórico."""
    return user_is_agenda_manager(
        user
    )


def user_can_see_event(
    user,
    event,
    active_team_id="all",
):
    """Compatibilidad con el servicio histórico."""
    return user_can_view_event(
        user,
        event,
        active_team_id=active_team_id,
    )


def events_between_for_user(
    user,
    start,
    end,
    base_qs,
    active_team_id="all",
):
    """Ventana temporal y ámbito multiempresa centralizado."""
    queryset = (
        visible_events_for_user(
            user,
            active_team_id=active_team_id,
            queryset=base_qs,
        )
        .filter(start__lt=end)
        .filter(
            models.Q(end__gte=start)
            | models.Q(end__isnull=True)
        )
        .select_related(
            "calendar",
            "created_by",
            "updated_by",
            "team",
        )
        .prefetch_related(
            "who_users",
        )
    )

    return queryset
