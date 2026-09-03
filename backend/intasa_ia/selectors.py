ALL_TEAM_VALUES = {
    None,
    "",
    "0",
    0,
    "all",
    "ALL",
    "todas",
    "Todas",
}


class IAContextError(ValueError):
    """No se puede determinar un ámbito empresarial seguro."""


def allowed_ia_teams(user):
    if not getattr(user, "is_authenticated", False):
        return user.teams.none()

    if getattr(user, "is_superuser", False):
        from usuarios.models import Team

        return Team.objects.all().order_by("id")

    return user.teams.all().order_by("id")


def resolve_ia_team(request):
    teams = allowed_ia_teams(request.user)

    active_team_id = request.session.get(
        "active_team_id"
    )

    if active_team_id not in ALL_TEAM_VALUES:
        try:
            active_team_id = int(active_team_id)
        except (TypeError, ValueError) as exc:
            raise IAContextError(
                "La empresa activa no es válida."
            ) from exc

        team = teams.filter(pk=active_team_id).first()

        if team is None:
            raise IAContextError(
                "No tienes acceso a la empresa seleccionada."
            )

        return team

    count = teams.count()

    if count == 1:
        return teams.first()

    if count == 0:
        raise IAContextError(
            "Tu usuario no pertenece a ninguna empresa."
        )

    raise IAContextError(
        "Selecciona una empresa concreta en el selector "
        "superior antes de iniciar una conversación."
    )
