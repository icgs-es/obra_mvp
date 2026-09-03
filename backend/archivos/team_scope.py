from django.apps import apps


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


class DocumentTeamResolutionError(ValueError):
    """No se puede determinar una empresa documental segura."""


def allowed_document_teams(user):
    Team = apps.get_model("usuarios", "Team")

    if not getattr(user, "is_authenticated", False):
        return Team.objects.none()

    if getattr(user, "is_superuser", False):
        return Team.objects.all().order_by("id")

    return user.teams.all().order_by("id")


def resolve_document_team(
    request,
    *,
    folder=None,
):
    """
    Obtiene la empresa de una nueva operación documental.

    Prioridad:
    1. Empresa ya fijada en la carpeta.
    2. Empresa activa numérica y permitida.
    3. Única empresa permitida del usuario.

    Nunca selecciona arbitrariamente la primera empresa cuando existen varias.
    """

    user = getattr(request, "user", None)

    teams = allowed_document_teams(user)

    if folder is not None and getattr(folder, "team_id", None):
        team = teams.filter(pk=folder.team_id).first()

        if team is None:
            raise DocumentTeamResolutionError(
                "No tienes acceso a la empresa asignada "
                "a esta carpeta documental."
            )

        return team

    try:
        active_team_id = request.session.get(
            "active_team_id"
        )
    except Exception:
        active_team_id = None

    if active_team_id not in ALL_TEAM_VALUES:
        try:
            active_team_id = int(active_team_id)
        except (TypeError, ValueError) as exc:
            raise DocumentTeamResolutionError(
                "La empresa activa de la sesión no es válida."
            ) from exc

        team = teams.filter(pk=active_team_id).first()

        if team is None:
            raise DocumentTeamResolutionError(
                "La empresa activa no está permitida "
                "para tu usuario."
            )

        return team

    UserProfile = apps.get_model(
        "usuarios",
        "UserProfile",
    )

    default_team_id = (
        UserProfile.objects
        .filter(user_id=user.pk)
        .values_list(
            "empresa_documental_predeterminada_id",
            flat=True,
        )
        .first()
    )

    if default_team_id:
        default_team = teams.filter(
            pk=default_team_id
        ).first()

        if default_team is None:
            raise DocumentTeamResolutionError(
                "La empresa documental predeterminada "
                "ya no está permitida para tu usuario. "
                "Contacta con administración."
            )

        return default_team

    count = teams.count()

    if count == 1:
        return teams.first()

    if count == 0:
        raise DocumentTeamResolutionError(
            "Tu usuario no pertenece a ninguna empresa. "
            "Contacta con administración."
        )

    raise DocumentTeamResolutionError(
        "Selecciona una empresa concreta en el selector "
        "superior antes de crear carpetas o subir archivos."
    )
