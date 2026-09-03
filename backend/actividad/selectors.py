from datetime import datetime

from django.db.models import Q, QuerySet

from .models import ActividadPlataforma


VALORES_TODAS_EMPRESAS = {
    None,
    "",
    "0",
    0,
    "all",
    "ALL",
    "todas",
    "Todas",
}


def _team_ids_usuario(user) -> list[int]:
    if not getattr(user, "is_authenticated", False):
        return []

    return list(
        user.teams.values_list("id", flat=True)
    )


def actividad_visible_para_usuario(
    *,
    user,
    active_team_id=None,
    alcance="equipo",
    modulo=None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
) -> QuerySet:
    """
    Devuelve únicamente actividad visible y permitida.

    Reglas iniciales:

    - ACTOR: solo puede verla el propio actor.
    - EQUIPO: usuarios vinculados al Team.
    - OBJETO: solo el actor hasta que cada módulo aporte
      su comprobación específica de permisos.
    - view_all_activity: permite consultar toda la actividad.
    """

    qs = ActividadPlataforma.objects.filter(
        visible_en_dashboard=True,
    ).select_related(
        "actor",
        "team",
    )

    if not getattr(user, "is_authenticated", False):
        return qs.none()

    puede_ver_todo = user.has_perm(
        "actividad.view_all_activity"
    )

    team_ids = _team_ids_usuario(user)

    if not puede_ver_todo:
        visibilidad_permitida = (
            Q(
                visibilidad=(
                    ActividadPlataforma.Visibilidad.ACTOR
                ),
                actor=user,
            )
            |
            Q(
                visibilidad=(
                    ActividadPlataforma.Visibilidad.EQUIPO
                ),
                team_id__in=team_ids,
            )
            |
            Q(
                visibilidad=(
                    ActividadPlataforma.Visibilidad.OBJETO
                ),
                actor=user,
            )
        )

        qs = qs.filter(visibilidad_permitida)

    if active_team_id not in VALORES_TODAS_EMPRESAS:
        try:
            selected_team_id = int(active_team_id)
        except (TypeError, ValueError):
            return qs.none()

        if (
            not puede_ver_todo
            and selected_team_id not in team_ids
        ):
            return qs.none()

        qs = qs.filter(team_id=selected_team_id)

    alcance = str(alcance or "equipo").strip().lower()

    if alcance == "mi":
        qs = qs.filter(actor=user)
    elif alcance != "equipo":
        return qs.none()

    if modulo:
        qs = qs.filter(
            modulo__iexact=str(modulo).strip()
        )

    if desde is not None:
        qs = qs.filter(ocurrida_en__gte=desde)

    if hasta is not None:
        qs = qs.filter(ocurrida_en__lt=hasta)

    return qs.order_by("-ocurrida_en", "-id")


def modulos_visibles_para_usuario(
    *,
    user,
    active_team_id=None,
    alcance="equipo",
) -> list[str]:
    return list(
        actividad_visible_para_usuario(
            user=user,
            active_team_id=active_team_id,
            alcance=alcance,
        )
        .order_by("modulo")
        .values_list("modulo", flat=True)
        .distinct()
    )
