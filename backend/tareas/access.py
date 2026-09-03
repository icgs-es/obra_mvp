from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Tarea


User = get_user_model()


ALL_TEAM_VALUES = {
    None,
    "",
    "all",
    "todas",
    "todos",
    "*",
}


def _normalized_active_team_id(value):
    if value is None:
        return None

    return str(value).strip().lower()


def resolve_active_task_team(request):
    """Resuelve exclusivamente un Team numérico permitido.

    No existe fallback cuando el selector está en
    «Todas sus empresas», está ausente o es inválido.
    """
    user = request.user

    if not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return None

    raw_value = request.session.get(
        "active_team_id"
    )

    normalized = _normalized_active_team_id(
        raw_value
    )

    if not normalized or not normalized.isdigit():
        return None

    if user.is_superuser:
        from usuarios.models import Team

        return Team.objects.filter(pk=int(normalized)).first()

    return user.teams.filter(pk=int(normalized)).first()


def _selected_team_ids(
    user,
    active_team_id,
):
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

    normalized = _normalized_active_team_id(
        active_team_id
    )

    if normalized in ALL_TEAM_VALUES:
        return allowed_ids

    if normalized and normalized.isdigit():
        selected_id = int(normalized)

        if selected_id in allowed_ids:
            return {
                selected_id,
            }

    return set()


def visible_tasks_for_user(
    user,
    *,
    active_team_id=None,
    queryset=None,
):
    """Devuelve exclusivamente tareas visibles para el usuario.

    Reglas:
    - Históricas sin Team: solo creador o asignado.
    - Privadas con Team: solo creador o asignado.
    - Departamento/global con Team: miembros del Team.
    - Un selector numérico limita al Team seleccionado.
    - «Todas» permite los Teams asignados al usuario.
    """
    if not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return Tarea.objects.none()

    queryset = (
        queryset
        if queryset is not None
        else Tarea.objects.all()
    )

    selected_team_ids = _selected_team_ids(
        user,
        active_team_id,
    )

    if user.is_superuser:
        scope = Q(team__isnull=True)
        if selected_team_ids:
            scope |= Q(team_id__in=selected_team_ids)
        return queryset.filter(scope).distinct()

    legacy_scope = (
        Q(team__isnull=True)
        & (
            Q(creador=user)
            | Q(asignados=user)
        )
    )

    team_scope = Q(pk__in=[])

    if selected_team_ids:
        team_scope = (
            Q(team_id__in=selected_team_ids)
            & (
                Q(
                    visibilidad__in=[
                        "depto",
                        "global",
                    ]
                )
                | Q(creador=user)
                | Q(asignados=user)
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


def editable_tasks_for_user(
    user,
    *,
    active_team_id=None,
    queryset=None,
):
    """Tareas editables: creador o asignado dentro del ámbito."""
    if not getattr(
        user,
        "is_authenticated",
        False,
    ):
        return Tarea.objects.none()

    queryset = (
        queryset
        if queryset is not None
        else Tarea.objects.all()
    )

    selected_team_ids = _selected_team_ids(
        user,
        active_team_id,
    )

    if user.is_superuser:
        scope = Q(team__isnull=True)
        if selected_team_ids:
            scope |= Q(team_id__in=selected_team_ids)
        return queryset.filter(scope).distinct()

    legacy_scope = (
        Q(team__isnull=True)
        & (
            Q(creador=user)
            | Q(asignados=user)
        )
    )

    team_scope = Q(pk__in=[])

    if selected_team_ids:
        team_scope = Q(team_id__in=selected_team_ids) & (
            Q(creador=user) | Q(asignados=user)
        )

        if (
            user.has_perm("tareas.change_tarea")
            or user.groups.filter(name__in=["Gerencia", "Administradores"]).exists()
        ):
            team_scope |= Q(
                team_id__in=selected_team_ids,
                visibilidad__in=["depto", "global"],
            )

    return (
        queryset
        .filter(
            legacy_scope
            | team_scope
        )
        .distinct()
    )


def assignee_queryset_for_task(
    *,
    user,
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
        if instance.creador_id:
            allowed_ids.add(
                instance.creador_id
            )

        allowed_ids.update(
            instance.asignados.values_list(
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
