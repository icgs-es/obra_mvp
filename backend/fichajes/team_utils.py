def resolve_team_for_user(user, request=None):
    teams_qs = user.teams.all().order_by("id")
    team_count = teams_qs.count()

    if team_count == 0:
        return None, "Tu usuario no pertenece a ninguna empresa. Contacta con administración antes de fichar."

    active_team_id = None
    if request is not None:
        active_team_id = request.session.get("active_team_id")

    if active_team_id and str(active_team_id) != "all":
        team = teams_qs.filter(id=active_team_id).first()
        if team:
            return team, ""

    if team_count == 1:
        return teams_qs.first(), ""

    return None, "Tu usuario pertenece a varias empresas. Selecciona una empresa activa antes de fichar."
