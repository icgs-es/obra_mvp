from __future__ import annotations

from django.contrib.auth import (
    get_user_model,
)
from django.db.models import Q

from .models import (
    Calendar,
    Event,
)


User = get_user_model()


ALL_TEAM_VALUES = {
    None,
    "",
    "0",
    "all",
    "todas",
    "todos",
    "*",
}


CALENDAR_TYPES_BY_VISIBILITY = {
    Event.Visibility.PRIVADA: (
        "PERSONAL",
        "PRIVATE",
    ),
    Event.Visibility.DEPARTAMENTO: (
        "DEPARTAMENTO",
        "TEAM",
    ),
    Event.Visibility.GLOBAL: (
        "GLOBAL",
        "ORG",
    ),
}


RECOGNIZED_CALENDAR_TYPES = {
    calendar_type
    for values
    in CALENDAR_TYPES_BY_VISIBILITY.values()
    for calendar_type
    in values
}


def _normalize_team_value(value):
    if value is None:
        return None

    return str(value).strip().lower()


def user_is_agenda_manager(user):
    """Gerencia operativa sin bypass entre empresas."""
    if not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return False

    if user.is_superuser:
        return True

    if user.has_perm("agenda.change_event"):
        return True

    return user.groups.filter(
        name__in=[
            "Gerencia",
            "Administradores",
        ]
    ).exists()


def resolve_active_agenda_team(request):
    """Resuelve únicamente una empresa explícita y autorizada.

    No selecciona la primera empresa del usuario.
    No concede la primera empresa del sistema a staff.
    """
    user = request.user

    if not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return None

    value = _normalize_team_value(
        request.session.get(
            "active_team_id"
        )
    )

    if not value or not value.isdigit():
        return None

    if user.is_superuser:
        from usuarios.models import Team

        return Team.objects.filter(pk=int(value)).first()

    return user.teams.filter(pk=int(value)).first()


def selected_agenda_team_ids(
    user,
    active_team_id,
):
    """Teams visibles según el selector de empresa."""
    if not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return set()

    if user.is_superuser:
        from usuarios.models import Team

        allowed_ids = set(Team.objects.values_list("pk", flat=True))
    else:
        allowed_ids = set(
            user.teams.values_list(
                "pk",
                flat=True,
            )
        )

    value = _normalize_team_value(
        active_team_id
    )

    if value in ALL_TEAM_VALUES:
        return allowed_ids

    if value and value.isdigit():
        selected_id = int(value)

        if selected_id in allowed_ids:
            return {
                selected_id,
            }

    return set()


def calendar_matches_visibility(
    calendar,
    visibility,
    *,
    user=None,
):
    """Comprueba coherencia entre capa y calendario."""
    if calendar is None:
        return False

    visibility = str(
        visibility
        or Event.Visibility.PRIVADA
    ).upper()

    allowed_types = (
        CALENDAR_TYPES_BY_VISIBILITY
        .get(visibility)
    )

    if not allowed_types:
        return False

    if str(calendar.tipo).upper() not in (
        allowed_types
    ):
        return False

    if (
        visibility
        == Event.Visibility.PRIVADA
        and user is not None
        and calendar.owner_id
        not in {
            None,
            user.pk,
        }
    ):
        return False

    return True


def available_calendars_for_event(
    *,
    user=None,
    instance=None,
):
    """Calendarios reconocidos y utilizables.

    Conserva los tres tipos legacy:
    PRIVATE, TEAM y ORG.
    """
    recognized = Q(
        activo=True,
        tipo__in=(
            RECOGNIZED_CALENDAR_TYPES
        ),
    )

    if user is not None:
        personal_types = (
            CALENDAR_TYPES_BY_VISIBILITY[
                Event.Visibility.PRIVADA
            ]
        )

        recognized &= (
            ~Q(tipo__in=personal_types)
            | Q(owner__isnull=True)
            | Q(owner=user)
        )

    queryset = Calendar.objects.filter(
        recognized
    )

    if (
        instance is not None
        and getattr(
            instance,
            "calendar_id",
            None,
        )
    ):
        queryset = Calendar.objects.filter(
            Q(pk=instance.calendar_id)
            | Q(pk__in=queryset)
        )

    return queryset.order_by(
        "tipo",
        "nombre",
        "pk",
    ).distinct()


def resolve_calendar_for_event(
    *,
    user,
    visibility,
    explicit_id=None,
):
    """Resuelve calendario sin fallback entre capas."""
    queryset = available_calendars_for_event(
        user=user
    )

    if explicit_id not in {
        None,
        "",
    }:
        try:
            explicit_id = int(
                explicit_id
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

        calendar = queryset.filter(
            pk=explicit_id
        ).first()

        if not calendar_matches_visibility(
            calendar,
            visibility,
            user=user,
        ):
            return None

        return calendar

    visibility = str(
        visibility
        or Event.Visibility.PRIVADA
    ).upper()

    allowed_types = (
        CALENDAR_TYPES_BY_VISIBILITY
        .get(visibility)
    )

    if not allowed_types:
        return None

    candidates = queryset.filter(
        tipo__in=allowed_types
    )

    if (
        visibility
        == Event.Visibility.PRIVADA
    ):
        owned = candidates.filter(
            owner=user
        ).first()

        if owned is not None:
            return owned

        return candidates.filter(
            owner__isnull=True
        ).first()

    return candidates.first()


def assignee_queryset_for_event(
    *,
    user=None,
    team=None,
    instance=None,
):
    """Usuarios seleccionables sin cruzar empresas."""
    if team is not None:
        return (
            User.objects
            .filter(
                is_active=True,
                teams=team,
            )
            .order_by("username")
            .distinct()
        )

    # Compatibilidad temporal para llamadas antiguas.
    # Las vistas endurecidas pasarán siempre user/team.
    if user is None and instance is None:
        return (
            User.objects
            .filter(is_active=True)
            .order_by("username")
        )

    allowed_ids = set()

    if (
        user is not None
        and getattr(
            user,
            "pk",
            None,
        )
    ):
        allowed_ids.add(user.pk)

    if (
        instance is not None
        and getattr(
            instance,
            "pk",
            None,
        )
    ):
        if instance.created_by_id:
            allowed_ids.add(
                instance.created_by_id
            )

        allowed_ids.update(
            instance.who_users.values_list(
                "pk",
                flat=True,
            )
        )

    return (
        User.objects
        .filter(
            is_active=True,
            pk__in=allowed_ids,
        )
        .order_by("username")
    )


def visible_events_for_user(
    user,
    *,
    active_team_id="all",
    queryset=None,
):
    """Eventos visibles para un usuario.

    Reglas:
    - Privado con Team: solo creador.
    - Departamento/Global: miembros del Team seleccionado.
    - Legacy sin Team:
      · privado: solo creador;
      · compartido: creador o asistentes.
    - Sin bypass global por staff/superuser.
    """
    if not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return Event.objects.none()

    queryset = (
        queryset
        if queryset is not None
        else Event.objects.all()
    )

    # Agenda pertenece al dominio de personas.
    # Gerencia/gestores funcionales pueden consultar la Agenda
    # organizativa completa sin depender del Team empresarial.
    #
    # Esto NO concede permisos administrativos generales ni
    # modifica el aislamiento Team de otros módulos.
    if user_is_agenda_manager(user):
        return queryset.distinct()

    selected_ids = (
        selected_agenda_team_ids(
            user,
            active_team_id,
        )
    )

    shared_values = [
        Event.Visibility.DEPARTAMENTO,
        Event.Visibility.GLOBAL,
    ]

    legacy_scope = (
        Q(
            team__isnull=True,
            visibility=(
                Event.Visibility.PRIVADA
            ),
            created_by=user,
        )
        |
        (
            Q(
                team__isnull=True,
                visibility__in=shared_values,
            )
            & (
                Q(created_by=user)
                | Q(who_users=user)
            )
        )
    )

    team_scope = Q(pk__in=[])

    if selected_ids:
        team_scope = (
            Q(
                team_id__in=selected_ids,
                visibility=(
                    Event.Visibility.PRIVADA
                ),
                created_by=user,
            )
            |
            Q(
                team_id__in=selected_ids,
                visibility__in=shared_values,
            )
        )

    return (
        queryset
        .filter(
            legacy_scope
            | team_scope
        )
        .distinct()
    )


def editable_events_for_user(
    user,
    *,
    active_team_id="all",
    queryset=None,
):
    """Eventos editables dentro del ámbito autorizado.

    - Privado: solo creador.
    - Compartido: creador, asistente o Gerencia,
      siempre dentro de un Team permitido.
    - Legacy sin Team: creador o asistente;
      no existe bypass gerencial.
    """
    if not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return Event.objects.none()

    queryset = (
        queryset
        if queryset is not None
        else Event.objects.all()
    )

    selected_ids = (
        selected_agenda_team_ids(
            user,
            active_team_id,
        )
    )

    if user.is_superuser:
        scope = Q(team__isnull=True)
        if selected_ids:
            scope |= Q(team_id__in=selected_ids)
        return queryset.filter(scope).distinct()

    shared_values = [
        Event.Visibility.DEPARTAMENTO,
        Event.Visibility.GLOBAL,
    ]

    legacy_scope = (
        Q(
            team__isnull=True,
            visibility=(
                Event.Visibility.PRIVADA
            ),
            created_by=user,
        )
        |
        (
            Q(
                team__isnull=True,
                visibility__in=shared_values,
            )
            & (
                Q(created_by=user)
                | Q(who_users=user)
            )
        )
    )

    team_scope = Q(pk__in=[])

    if selected_ids:
        private_scope = Q(
            team_id__in=selected_ids,
            visibility=(
                Event.Visibility.PRIVADA
            ),
            created_by=user,
        )

        shared_scope = Q(
            team_id__in=selected_ids,
            visibility__in=shared_values,
        )

        if not user_is_agenda_manager(
            user
        ):
            shared_scope &= (
                Q(created_by=user)
                | Q(who_users=user)
            )

        team_scope = (
            private_scope
            | shared_scope
        )

    return (
        queryset
        .filter(
            legacy_scope
            | team_scope
        )
        .distinct()
    )


def user_can_view_event(
    user,
    event,
    *,
    active_team_id="all",
):
    if not getattr(
        event,
        "pk",
        None,
    ):
        return False

    return visible_events_for_user(
        user,
        active_team_id=active_team_id,
        queryset=Event.objects.filter(
            pk=event.pk
        ),
    ).exists()


def user_can_edit_event(
    user,
    event,
    *,
    active_team_id="all",
):
    if not getattr(
        event,
        "pk",
        None,
    ):
        return False

    return editable_events_for_user(
        user,
        active_team_id=active_team_id,
        queryset=Event.objects.filter(
            pk=event.pk
        ),
    ).exists()
