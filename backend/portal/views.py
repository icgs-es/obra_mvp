from collections import Counter
from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from actividad.selectors import (
    VALORES_TODAS_EMPRESAS,
    actividad_visible_para_usuario,
)
from usuarios.models import Team
from agenda.integration import personal_agenda_payload
from agenda.user_colors import build_user_color_map

from .activity_presentation import (
    ACTIVITY_GROUP_LIMIT,
    ACTIVITY_RAW_LIMIT,
    compactar_actividades,
)


ACTIVITY_MODULE_PRESENTATION = {
    "archivos": {
        "label": "Archivos",
        "icon": "bi-folder2-open",
        "badge": "text-bg-primary",
    },
    "gestion": {
        "label": "Gestión",
        "icon": "bi-receipt",
        "badge": "text-bg-success",
    },
    "tareas": {
        "label": "Tareas",
        "icon": "bi-check2-square",
        "badge": "text-bg-warning",
    },
    "agenda": {
        "label": "Agenda",
        "icon": "bi-calendar-event",
        "badge": "text-bg-info",
    },
    "obra_movil": {
        "label": "Obra móvil",
        "icon": "bi-phone",
        "badge": "text-bg-secondary",
    },
    "planificacion_obra": {
        "label": "Planificación",
        "icon": "bi-building-gear",
        "badge": "text-bg-dark",
    },
    "almacen": {
        "label": "Almacén",
        "icon": "bi-box-seam",
        "badge": "text-bg-secondary",
    },
    "fichajes": {
        "label": "Fichajes",
        "icon": "bi-clock-history",
        "badge": "text-bg-light",
    },
}


def _inicio_dia_local(fecha):
    return timezone.make_aware(
        datetime.combine(fecha, time.min),
        timezone.get_current_timezone(),
    )


def _module_presentation(modulo):
    key = str(modulo or "").strip().lower()

    default = {
        "label": (
            key.replace("_", " ").title()
            or "Actividad"
        ),
        "icon": "bi-activity",
        "badge": "text-bg-secondary",
    }

    return key, ACTIVITY_MODULE_PRESENTATION.get(
        key,
        default,
    )


def _presentar_actividad(actividad):
    modulo_key, presentation = (
        _module_presentation(
            actividad.modulo
        )
    )

    actividad.modulo_key = modulo_key
    actividad.modulo_label = (
        presentation["label"]
    )
    actividad.modulo_icon = (
        presentation["icon"]
    )
    actividad.modulo_badge_class = (
        presentation["badge"]
    )

    metadata = (
        actividad.metadata
        if isinstance(actividad.metadata, dict)
        else {}
    )

    nombres = metadata.get("nombres") or []

    if not isinstance(nombres, list):
        nombres = []

    actividad.detalle_nombres = [
        str(nombre)
        for nombre in nombres[:3]
        if str(nombre).strip()
    ]

    cantidad = metadata.get("cantidad") or 0

    try:
        cantidad = int(cantidad)
    except (TypeError, ValueError):
        cantidad = 0

    actividad.detalle_restantes = max(
        cantidad - len(
            actividad.detalle_nombres
        ),
        0,
    )

    actividad.ocurrida_local = (
        timezone.localtime(
            actividad.ocurrida_en
        )
    )

    return actividad


def _activity_scope_label(
    *,
    user,
    active_team_id,
):
    if active_team_id in VALORES_TODAS_EMPRESAS:
        return "Todas tus empresas"

    try:
        selected_team_id = int(
            active_team_id
        )
    except (TypeError, ValueError):
        return "Empresa no disponible"

    if user.has_perm(
        "actividad.view_all_activity"
    ):
        team_qs = Team.objects.all()
    else:
        team_qs = user.teams.all()

    team = (
        team_qs
        .filter(pk=selected_team_id)
        .only("id", "name")
        .first()
    )

    if team is None:
        return "Empresa no disponible"

    return team.name


def _normalizar_alcance(raw):
    alcance = str(
        raw or "equipo"
    ).strip().lower()

    if alcance not in {
        "equipo",
        "mi",
    }:
        return "equipo"

    return alcance


def _normalizar_modulo(raw):
    return str(raw or "").strip().lower()


def _dashboard_activity_context(request):
    hoy = timezone.localdate()
    ayer = hoy - timedelta(days=1)

    inicio_hoy = _inicio_dia_local(hoy)
    inicio_ayer = _inicio_dia_local(ayer)

    inicio_semana_fecha = (
        hoy - timedelta(days=hoy.weekday())
    )

    inicio_semana = _inicio_dia_local(
        inicio_semana_fecha
    )

    active_team_id = request.session.get(
        "active_team_id",
        "all",
    )

    alcance = _normalizar_alcance(
        request.GET.get(
            "actividad_alcance"
        )
    )

    modulo_activo = _normalizar_modulo(
        request.GET.get(
            "actividad_modulo"
        )
    )

    actividad_equipo_semana_qs = (
        actividad_visible_para_usuario(
            user=request.user,
            active_team_id=active_team_id,
            alcance="equipo",
            desde=inicio_semana,
        )
    )

    actividad_mia_semana_count = (
        actividad_equipo_semana_qs
        .filter(actor=request.user)
        .count()
    )

    module_counter = Counter(
        str(modulo or "").strip().lower()
        for modulo in (
            actividad_equipo_semana_qs
            .values_list(
                "modulo",
                flat=True,
            )
        )
    )

    module_filters = []

    for modulo_key, count in sorted(
        module_counter.items(),
        key=lambda item: (
            -item[1],
            item[0],
        ),
    ):
        if not modulo_key:
            continue

        _key, presentation = (
            _module_presentation(
                modulo_key
            )
        )

        module_filters.append(
            {
                "value": modulo_key,
                "label": presentation["label"],
                "icon": presentation["icon"],
                "count": count,
            }
        )

    actividad_qs = (
        actividad_visible_para_usuario(
            user=request.user,
            active_team_id=active_team_id,
            alcance=alcance,
            modulo=(
                modulo_activo
                if modulo_activo
                else None
            ),
            desde=inicio_semana,
        )
    )

    actividad_semana_count = (
        actividad_qs.count()
    )

    actividad_hoy_count = (
        actividad_qs
        .filter(
            ocurrida_en__gte=inicio_hoy,
        )
        .count()
    )

    actividades_individuales = [
        _presentar_actividad(actividad)
        for actividad
        in actividad_qs[:ACTIVITY_RAW_LIMIT]
    ]

    actividades_compactadas = (
        compactar_actividades(
            actividades_individuales
        )
    )

    actividad_grupos_total = len(
        actividades_compactadas
    )

    actividades = actividades_compactadas[
        :ACTIVITY_GROUP_LIMIT
    ]

    grupos = {
        "hoy": [],
        "ayer": [],
        "semana": [],
    }

    for actividad in actividades:
        fecha_local = (
            actividad.ocurrida_local.date()
        )

        if fecha_local == hoy:
            grupos["hoy"].append(
                actividad
            )
        elif fecha_local == ayer:
            grupos["ayer"].append(
                actividad
            )
        else:
            grupos["semana"].append(
                actividad
            )

    actividad_grupos = [
        {
            "key": "hoy",
            "label": "Hoy",
            "items": grupos["hoy"],
        },
        {
            "key": "ayer",
            "label": "Ayer",
            "items": grupos["ayer"],
        },
        {
            "key": "semana",
            "label": "Esta semana",
            "items": grupos["semana"],
        },
    ]

    actividad_grupos = [
        grupo
        for grupo in actividad_grupos
        if grupo["items"]
    ]

    return {
        "actividad_grupos": (
            actividad_grupos
        ),
        "actividad_hoy_count": (
            actividad_hoy_count
        ),
        "actividad_semana_count": (
            actividad_semana_count
        ),
        "actividad_mia_semana_count": (
            actividad_mia_semana_count
        ),
        "actividad_scope_label": (
            _activity_scope_label(
                user=request.user,
                active_team_id=active_team_id,
            )
        ),
        "actividad_alcance": alcance,
        "actividad_modulo_activo": (
            modulo_activo
        ),
        "actividad_module_filters": (
            module_filters
        ),
        "actividad_limite": (
            ACTIVITY_GROUP_LIMIT
        ),
        "actividad_grupos_total": (
            actividad_grupos_total
        ),
        "actividad_individuales_consultadas": (
            len(actividades_individuales)
        ),
    }


@login_required
def dashboard(request):
    hoy = timezone.localdate()
    ahora = timezone.localtime()

    ctx = {
        "hoy": hoy,
        "ahora": ahora,
    }

    ctx.update(
        _dashboard_activity_context(request)
    )
    ctx["agenda_personal"] = personal_agenda_payload(
        request.user,
        build_user_color_map(),
        active_team_id=request.session.get("active_team_id", "all"),
    )

    return render(
        request,
        "portal/index.html",
        ctx,
    )


@login_required
def app_home(request):
    return dashboard(request)
