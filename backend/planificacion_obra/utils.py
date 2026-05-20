def get_allowed_teams(request):
    """
    Empresas que el usuario puede gestionar.
    Team = Empresa.
    """
    if not request.user.is_authenticated:
        return request.user.teams.none()
    return request.user.teams.all()


def get_active_team(request):
    """
    Devuelve:
    - Team concreto si hay empresa activa.
    - None si está seleccionada 'Todas las empresas'.
    - Primer Team permitido si no hay selección previa.
    """
    teams = get_allowed_teams(request)
    active_team_id = request.session.get("active_team_id")

    if active_team_id == "all":
        return None

    if active_team_id:
        team = teams.filter(id=active_team_id).first()
        if team:
            return team

    return teams.first()


def filter_by_active_team(qs, request):
    """
    Filtra cualquier QuerySet con campo team respetando permisos.
    """
    teams = get_allowed_teams(request)
    active_team = get_active_team(request)

    if active_team is None:
        return qs.filter(team__in=teams)

    return qs.filter(team=active_team)


def user_can_access_team(request, team):
    if team is None:
        return False
    return get_allowed_teams(request).filter(id=team.id).exists()
