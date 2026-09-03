from decimal import Decimal
from django.contrib import messages
from django.db import transaction
from .activity_recursos_reales import (
    registrar_cambio_recurso_real_manual,
    registrar_creacion_recursos_reales_manuales,
    registrar_eliminacion_recurso_real_manual,
    snapshot_recurso_real,
)

from .activity import (
    registrar_cambio_asignacion,
    registrar_creacion_asignacion,
    registrar_eliminacion_asignacion,
    registrar_realizacion_asignacion,
    registrar_repeticion_asignaciones,
    snapshot_asignacion,
)
from datetime import datetime
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from .models import (
    AlmacenObra,
    AsignacionObra,
    CapituloCatalogo,
    EmpleadoObra,
    ObraPlanificacion,
    PartidaCatalogo,
    RecursoCatalogo,
    TareaObra,
    UnidadObra,
)
from .utils import filter_by_active_team, get_active_team
from .forms import AsignacionObraForm
from rrhh.models import Empleado


from .models import (
    FaseObra,
    TareaRecursoPrevisto,
    TareaRecursoReal,
    RecursoAlmacenMovimiento,
)

REPORTS_DIR = Path("/app/reports/planificacion_obra")


def _sum_decimal(qs, field_name):
    value = qs.aggregate(total=Sum(field_name)).get("total")
    return value or Decimal("0")


def _coste_real(qs):
    total = _sum_decimal(qs, "costo_recurso_real")
    if total == 0:
        total = _sum_decimal(qs, "costo_recurso")
    return total


def _pct(real, previsto):
    if not previsto or previsto == 0:
        return None
    return (real * Decimal("100") / previsto).quantize(Decimal("0.01"))


def _obra_metricas(obra, request):
    def same_team(qs):
        if getattr(obra, "team_id", None):
            field_names = {f.name for f in qs.model._meta.fields}
            if "team" in field_names:
                return qs.filter(team_id=obra.team_id)
        return qs

    tareas = same_team(TareaObra.objects.filter(obra=obra))
    fases = same_team(FaseObra.objects.filter(obra=obra))
    unidades = same_team(UnidadObra.objects.filter(obra=obra))
    almacenes = same_team(AlmacenObra.objects.filter(obra=obra))

    previstos = same_team(
        TareaRecursoPrevisto.objects.filter(legacy_cod_obra=obra.legacy_cod_obra)
    )
    reales = same_team(
        TareaRecursoReal.objects.filter(legacy_cod_obra=obra.legacy_cod_obra)
    )
    movimientos = same_team(
        RecursoAlmacenMovimiento.objects.filter(legacy_cod_obra=obra.legacy_cod_obra)
    )

    coste_previsto = _sum_decimal(previstos, "costo_recurso")
    coste_real = _coste_real(reales)

    return {
        "fases_count": fases.count(),
        "unidades_count": unidades.count(),
        "tareas_count": tareas.count(),
        "tareas_incidencias_count": tareas.filter(con_incidencias=True).count(),
        "previstos_count": previstos.count(),
        "reales_count": reales.count(),
        "almacenes_count": almacenes.count(),
        "movimientos_count": movimientos.count(),
        "coste_previsto": coste_previsto,
        "coste_real": coste_real,
        "desviacion": coste_real - coste_previsto,
        "ejecucion_pct": _pct(coste_real, coste_previsto),
    }


@login_required
def index(request):
    # PI_PANEL_OBRA_UNIFICADO_V1
    # Panel de Obra pasa a ser el dashboard ejecutivo/económico.
    # Reutiliza la lógica de obras_list para evitar cálculos duplicados.
    return obras_list(request)


@login_required
def descargar_informe(request, filename):
    if "/" in filename or "\\" in filename or not filename.endswith(".csv"):
        raise Http404("Informe no válido")

    base_dir = REPORTS_DIR.resolve()
    file_path = (REPORTS_DIR / filename).resolve()

    try:
        file_path.relative_to(base_dir)
    except ValueError:
        raise Http404("Informe no válido")

    if not file_path.exists() or not file_path.is_file():
        raise Http404("Informe no encontrado")

    return FileResponse(
        open(file_path, "rb"),
        as_attachment=True,
        filename=filename,
        content_type="text/csv",
    )


@login_required

def _obras_scope_qs(request):
    active_team = get_active_team(request)

    qs = ObraPlanificacion.objects.select_related("team").all()

    if active_team is not None:
        qs = qs.filter(team=active_team)
    elif not request.user.is_superuser and hasattr(request.user, "teams"):
        qs = qs.filter(team__in=request.user.teams.all())

    return qs


def obras_list(request):
    from decimal import Decimal

    active_team = get_active_team(request)

    obras_qs = ObraPlanificacion.objects.select_related("team").all()

    if active_team is not None:
        obras_qs = obras_qs.filter(team=active_team)
    elif not request.user.is_superuser and hasattr(request.user, "teams"):
        obras_qs = obras_qs.filter(team__in=request.user.teams.all())

    obras_qs = obras_qs.order_by("team__name", "legacy_cod_obra", "nombre")

    rows = []

    for obra in obras_qs:
        metricas = _obra_metricas(obra, request)

        ejecucion_pct = metricas.get("ejecucion_pct") or Decimal("0")
        try:
            ejecucion_bar_pct = max(0, min(100, int(float(ejecucion_pct))))
        except Exception:
            ejecucion_bar_pct = 0

        desviacion = metricas.get("desviacion") or Decimal("0")
        coste_real = metricas.get("coste_real") or Decimal("0")

        if desviacion > 0:
            estado_economico = "SOBRECOSTE"
        elif coste_real > 0:
            estado_economico = "BAJO_PREVISTO"
        else:
            estado_economico = "SIN_REAL"

        rows.append({
            "obra": obra,
            "ejecucion_bar_pct": ejecucion_bar_pct,
            "estado_economico": estado_economico,
            **metricas,
        })

    total_previsto = sum((r.get("coste_previsto") or Decimal("0")) for r in rows)
    total_real = sum((r.get("coste_real") or Decimal("0")) for r in rows)
    total_desviacion = total_real - total_previsto
    ejecucion_global_pct = _pct(total_real, total_previsto)

    obras_con_real = len([r for r in rows if (r.get("coste_real") or Decimal("0")) > 0])
    obras_con_sobrecoste = len([r for r in rows if (r.get("desviacion") or Decimal("0")) > 0])
    obras_sin_sobrecoste = max(0, len(rows) - obras_con_sobrecoste)

    top_desviaciones = sorted(
        rows,
        key=lambda r: abs(r.get("desviacion") or Decimal("0")),
        reverse=True,
    )[:5]

    context = {
        "active_team": active_team,
        "modo_todas": active_team is None,
        "rows": rows,
        "obras_count": len(rows),
        "total_previsto": total_previsto,
        "total_real": total_real,
        "total_desviacion": total_desviacion,
        "ejecucion_global_pct": ejecucion_global_pct,
        "obras_con_real": obras_con_real,
        "obras_con_sobrecoste": obras_con_sobrecoste,
        "obras_sin_sobrecoste": obras_sin_sobrecoste,
        "top_desviaciones": top_desviaciones,

        # PI_PANEL_OBRA_UNIFICADO_V1 · KPIs técnicos integrados desde el antiguo Panel de Obra.
        "empleados_count": filter_by_active_team(EmpleadoObra.objects.all(), request).count(),
        "unidades_total_count": filter_by_active_team(UnidadObra.objects.all(), request).count(),
        "capitulos_count": filter_by_active_team(CapituloCatalogo.objects.all(), request).count(),
        "partidas_count": filter_by_active_team(PartidaCatalogo.objects.all(), request).count(),
        "tareas_obra_count": filter_by_active_team(TareaObra.objects.all(), request).count(),
        "asignaciones_count": filter_by_active_team(AsignacionObra.objects.all(), request).count(),
    }
    return render(request, "planificacion_obra/obras_list.html", context)


@login_required
def obra_detail(request, pk):
    obra = get_object_or_404(
        _obras_scope_qs(request),
        pk=pk,
    )

    metricas = _obra_metricas(obra, request)

    fases = filter_by_active_team(
        FaseObra.objects.filter(obra=obra).order_by("legacy_cod_fase", "nombre"),
        request,
    )

    fases_rows = []
    for fase in fases:
        unidades_count = filter_by_active_team(
            UnidadObra.objects.filter(obra=obra, fase=fase),
            request,
        ).count()

        tareas_count = filter_by_active_team(
            TareaObra.objects.filter(obra=obra, legacy_cod_fase=fase.legacy_cod_fase),
            request,
        ).count()

        reales_fase = filter_by_active_team(
            TareaRecursoReal.objects.filter(
                legacy_cod_obra=obra.legacy_cod_obra,
                legacy_cod_fase=fase.legacy_cod_fase,
            ),
            request,
        )

        fases_rows.append({
            "fase": fase,
            "unidades_count": unidades_count,
            "tareas_count": tareas_count,
            "coste_real": _coste_real(reales_fase),
        })

    reales = filter_by_active_team(
        TareaRecursoReal.objects.filter(legacy_cod_obra=obra.legacy_cod_obra),
        request,
    )

    tipo_costes = (
        reales
        .values("legacy_tipo_recurso")
        .annotate(total=Sum("costo_recurso_real"), lineas=Count("id"))
        .order_by("-total")[:12]
    )

    ultimas_tareas = (
        filter_by_active_team(TareaObra.objects.filter(obra=obra), request)
        .select_related("unidad_obra", "capitulo", "partida")
        .order_by("-inicio_real", "-inicio_tarea", "-id")[:25]
    )

    ultimos_movimientos = (
        filter_by_active_team(
            RecursoAlmacenMovimiento.objects.filter(legacy_cod_obra=obra.legacy_cod_obra),
            request,
        )
        .select_related("almacen", "recurso", "empleado", "partida")
        .order_by("-fecha_movimiento", "-legacy_id_movimiento")[:20]
    )

    context = {
        "obra": obra,
        "metricas": metricas,
        "fases_rows": fases_rows,
        "tipo_costes": tipo_costes,
        "ultimas_tareas": ultimas_tareas,
        "ultimos_movimientos": ultimos_movimientos,
    }
    return render(request, "planificacion_obra/obra_detail.html", context)


@login_required
def obra_tareas_list(request, pk):
    obra = get_object_or_404(
        _obras_scope_qs(request),
        pk=pk,
    )

    # La obra ya fue autorizada por _obras_scope_qs().
    # A partir de aquí se usa siempre el team real de la obra para no perder tareas
    # en modo "Todas las empresas" ni con superusuarios sin teams asociados.
    qs = (
        TareaObra.objects.filter(obra=obra, team=obra.team)
        .select_related("unidad_obra", "capitulo", "partida", "team")
        .order_by("legacy_cod_fase", "legacy_cod_vivienda", "inicio_tarea", "legacy_orden", "id")
    )

    fase = request.GET.get("fase") or ""
    capitulo_id = request.GET.get("capitulo") or ""
    partida_id = request.GET.get("partida") or ""
    incidencias = request.GET.get("incidencias") or ""
    q = (request.GET.get("q") or "").strip()

    if fase:
        qs = qs.filter(legacy_cod_fase=fase)

    if capitulo_id:
        qs = qs.filter(capitulo_id=capitulo_id)

    if partida_id:
        qs = qs.filter(partida_id=partida_id)

    if incidencias == "1":
        qs = qs.filter(con_incidencias=True)

    if q:
        qs = qs.filter(
            Q(programacion__icontains=q)
            | Q(legacy_key__icontains=q)
            | Q(legacy_cod_vivienda__icontains=q)
            | Q(legacy_planta__icontains=q)
            | Q(unidad_obra__edificio__icontains=q)
            | Q(unidad_obra__vivienda__icontains=q)
            | Q(unidad_obra__nivel__icontains=q)
            | Q(capitulo__nombre__icontains=q)
            | Q(partida__nombre__icontains=q)
            | Q(observaciones__icontains=q)
        )

    total_filtrado = qs.count()

    tareas = qs[:500]

    fases = (
        FaseObra.objects.filter(obra=obra, team=obra.team)
        .order_by("legacy_cod_fase", "nombre")
    )

    capitulos = (
        CapituloCatalogo.objects.filter(team=obra.team, tareas__obra=obra)
        .distinct()
        .order_by("codigo", "nombre")
    )

    partidas = (
        PartidaCatalogo.objects.filter(team=obra.team, tareas__obra=obra)
        .distinct()
        .order_by("codigo", "nombre")
    )

    context = {
        "obra": obra,
        "tareas": tareas,
        "total_filtrado": total_filtrado,
        "limite": 500,
        "fases": fases,
        "capitulos": capitulos,
        "partidas": partidas,
        "filtros": {
            "fase": str(fase),
            "capitulo": str(capitulo_id),
            "partida": str(partida_id),
            "incidencias": incidencias,
            "q": q,
        },
    }
    return render(request, "planificacion_obra/obra_tareas_list.html", context)



# FIX SAFE FALLBACK partidas_catalogo_by_code
# Evita NameError en asignaciones_list si el catálogo fallback no fue construido.
# La vista seguirá usando los otros catálogos disponibles; este dict vacío solo evita 500.
partidas_catalogo_by_code = {}

@login_required
def asignaciones_list(request):
    from types import SimpleNamespace
    from django.apps import apps
    from datetime import timedelta
    from django.db.models import Q
    from django.utils import timezone
    from django.utils.dateparse import parse_date
    import json

    AsignacionObra = apps.get_model("planificacion_obra", "AsignacionObra")
    TareaRecursoReal = apps.get_model("planificacion_obra", "TareaRecursoReal")
    ObraPlanificacion = apps.get_model("planificacion_obra", "ObraPlanificacion")
    TareaObra = apps.get_model("planificacion_obra", "TareaObra")
    Empleado = apps.get_model("rrhh", "Empleado")

    today = timezone.localdate()
    HISTORICO_REAL_DEFAULT_DAYS = 30

    fecha = request.GET.get("fecha") or ""
    fecha_desde = request.GET.get("fecha_desde") or ""
    fecha_hasta = request.GET.get("fecha_hasta") or ""
    obra_id = request.GET.get("obra") or ""
    # ASIGNACIONES_PRODUCCION_VIVIENDA_FILTERS_V1
    edificio_id = request.GET.get("edificio") or request.GET.get("fase") or ""
    vivienda_id = request.GET.get("vivienda") or ""
    planta_id = request.GET.get("planta") or ""

    # ASIGNACIONES_PERSONAL_ESTRUCTURA_REQUIERE_OBRA_V1
    # Igual que Planning de Obra: edificio/vivienda/planta solo tienen sentido
    # dentro de una obra seleccionada.
    if not obra_id:
        edificio_id = ""
        vivienda_id = ""
        planta_id = ""

    empleado_id = request.GET.get("empleado") or ""
    estado = request.GET.get("estado") or ""

    fecha_dt = parse_date(fecha) if fecha else None
    fecha_desde_dt = parse_date(fecha_desde) if fecha_desde else None
    fecha_hasta_dt = parse_date(fecha_hasta) if fecha_hasta else None

    def by_team(qs):
        if not request.user.is_superuser and hasattr(request.user, "teams"):
            return qs.filter(team__in=request.user.teams.all())
        return qs

    # ASIGNACIONES_PERSONAL_EDIFICIO_TEXTO_A_CODIGO_V1
    def _asig_norm_label(value):
        value = str(value or "").strip().upper()
        value = value.replace("·", " ")
        value = value.replace("-", " ")
        value = value.replace("_", " ")
        return " ".join(value.split())

    def _asig_unidad_nombre_fase_compat(unidad):
        if not unidad:
            return ""
        for field in [
            "edificio",
            "fase",
            "nombre_edificio",
            "nombre_fase",
            "descripcion_edificio",
            "descripcion_fase",
            "nombre",
            "descripcion",
            "titulo",
        ]:
            value = str(getattr(unidad, field, "") or "").strip()
            if value and value not in {"0", "-"}:
                return value
        return ""

    def _asig_resolver_edificio_id(value):
        raw = str(value or "").strip()
        if not raw:
            return ""
        if raw.isdigit():
            return raw

        target = _asig_norm_label(raw)

        qs_fases = TareaObra.objects.select_related("unidad_obra").exclude(
            legacy_cod_fase__isnull=True
        )
        if obra_id:
            qs_fases = qs_fases.filter(obra_id=obra_id)

        qs_fases = by_team(qs_fases).order_by("legacy_cod_fase", "id")

        vistos = set()
        for tarea_fase in qs_fases[:20000]:
            code = str(getattr(tarea_fase, "legacy_cod_fase", "") or "").strip()
            if not code or code in vistos:
                continue
            vistos.add(code)

            nombre = _asig_unidad_nombre_fase_compat(getattr(tarea_fase, "unidad_obra", None))
            candidatos = [
                code,
                nombre,
                f"{code} {nombre}",
                f"{code} · {nombre}",
            ]

            for cand in candidatos:
                if cand and _asig_norm_label(cand) == target:
                    return code

            # Compatibilidad: si llega solo "EDIFICIO I", buscar por nombre.
            if nombre and _asig_norm_label(nombre) == target:
                return code

        # Nunca dejar pasar texto a un campo numérico.
        return ""

    edificio_id = _asig_resolver_edificio_id(edificio_id)

    def str_or_dash(value):
        return str(value) if value else "-"

    def vivienda_label(cod):
        cod = str(cod or "").strip()
        if not cod or cod == "0":
            return "Obra"
        return f"Viv. {cod}"


    def _first_non_empty(obj, names):
        if not obj:
            return ""
        for name in names:
            value = getattr(obj, name, None)
            if value is not None:
                value = str(value).strip()
                if value:
                    return value
        return ""

    def _partida_info(partida_obj=None, fallback=""):
        fallback = str(fallback or "").strip()

        nombre = _first_non_empty(partida_obj, [
            "nombre",
            "descripcion",
            "descripcion_partida",
            "name",
            "titulo",
        ])

        codigo = _first_non_empty(partida_obj, [
            "codigo",
            "cod_partida",
            "legacy_partida",
            "referencia",
            "clave",
            "code",
        ])

        if not nombre and fallback:
            nombre = fallback

        if not codigo and fallback and nombre != fallback:
            codigo = fallback

        if not nombre:
            nombre = "-"

        codigo_visible = codigo if codigo and codigo != nombre else ""
        title = f"{codigo} · {nombre}" if codigo_visible else nombre

        return SimpleNamespace(
            nombre=nombre,
            codigo=codigo_visible,
            title=title,
        )


    def _safe_related(obj, name):
        if not obj:
            return None
        try:
            return getattr(obj, name, None)
        except Exception:
            return None

    def _catalog_display(obj=None, fallback=""):
        fallback = str(fallback or "").strip()

        nombre = _first_non_empty(obj, [
            "nombre",
            "descripcion",
            "descripcion_partida",
            "descripcion_capitulo",
            "name",
            "titulo",
        ])

        codigo = _first_non_empty(obj, [
            "codigo",
            "cod_partida",
            "cod_capitulo",
            "legacy_partida",
            "legacy_capitulo",
            "referencia",
            "clave",
            "code",
        ])

        if not nombre and fallback:
            nombre = fallback

        if not codigo and fallback and nombre != fallback:
            codigo = fallback

        if not nombre:
            nombre = "-"

        codigo_visible = codigo if codigo and codigo != nombre else ""
        title = f"{codigo} · {nombre}" if codigo_visible else nombre

        return SimpleNamespace(
            nombre=nombre,
            codigo=codigo_visible,
            title=title,
        )


    def _norm_catalog_code(value):
        value = str(value or "").strip().upper()
        return "".join(ch for ch in value if ch.isalnum())

    def _looks_like_catalog_code(value):
        value = str(value or "").strip()
        if not value:
            return False
        has_digit = any(ch.isdigit() for ch in value)
        allowed = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ.-_/ ")
        return has_digit and all(ch.upper() in allowed for ch in value)

    def _catalog_codes(obj):
        if not obj:
            return []
        codes = []
        for field in getattr(obj, "_meta", []).fields:
            name = field.name.lower()
            if "id" == name or name.endswith("_id"):
                continue
            if not any(tok in name for tok in ("cod", "codigo", "legacy", "clave", "referencia", "partida", "capitulo")):
                continue
            try:
                value = getattr(obj, field.name, None)
            except Exception:
                continue
            value = str(value or "").strip()
            if value and _looks_like_catalog_code(value):
                codes.append(value)
        return codes

    def _build_catalog_map(model):
        result = {}
        try:
            qs = model.objects.all()
        except Exception:
            return result

        for obj in qs:
            for code in _catalog_codes(obj):
                result[_norm_catalog_code(code)] = obj
        return result

    def _catalog_find(catalog_map, code):
        return catalog_map.get(_norm_catalog_code(code))

    def _capitulo_code_from_partida(code):
        code = str(code or "").strip()
        if "." in code:
            return code.split(".", 1)[0]
        return ""

    def _catalog_display_final(obj=None, fallback=""):
        fallback = str(fallback or "").strip()
        code = ""

        codes = _catalog_codes(obj)
        if codes:
            code = codes[0]
        elif fallback and _looks_like_catalog_code(fallback):
            code = fallback

        nombre = ""

        if obj:
            priority = ("nombre", "descripcion", "denominacion", "titulo", "name")
            for field in obj._meta.fields:
                fname = field.name.lower()
                if not any(tok in fname for tok in priority):
                    continue
                if field.get_internal_type() not in ("CharField", "TextField"):
                    continue
                value = str(getattr(obj, field.name, "") or "").strip()
                if value and value != code and not _looks_like_catalog_code(value):
                    nombre = value
                    break

            if not nombre:
                for field in obj._meta.fields:
                    if field.get_internal_type() not in ("CharField", "TextField"):
                        continue
                    fname = field.name.lower()
                    if "legacy" in fname or fname in ("codigo", "cod_partida", "cod_capitulo", "clave"):
                        continue
                    value = str(getattr(obj, field.name, "") or "").strip()
                    if value and value != code and not _looks_like_catalog_code(value):
                        nombre = value
                        break

        if not nombre and fallback and not _looks_like_catalog_code(fallback):
            nombre = fallback

        if not nombre:
            nombre = fallback or code or "-"

        codigo_visible = code if code and code != nombre else ""
        title = f"{codigo_visible} · {nombre}" if codigo_visible else nombre

        return SimpleNamespace(nombre=nombre, codigo=codigo_visible, title=title)

    # ------------------------------------------------------
    # PLANIFICADAS / REALIZADAS DESDE PORTAL
    # ------------------------------------------------------
    qs_plan = AsignacionObra.objects.select_related(
        "team", "empleado", "tarea_obra", "unidad_obra", "capitulo", "partida"
    )
    qs_plan = by_team(qs_plan)

    if fecha_dt:
        qs_plan = qs_plan.filter(fecha_inicio=fecha_dt)
    if fecha_desde_dt:
        qs_plan = qs_plan.filter(fecha_inicio__gte=fecha_desde_dt)
    if fecha_hasta_dt:
        qs_plan = qs_plan.filter(fecha_inicio__lte=fecha_hasta_dt)
    if obra_id:
        qs_plan = qs_plan.filter(tarea_obra__obra_id=obra_id)
    if edificio_id:
        qs_plan = qs_plan.filter(tarea_obra__legacy_cod_fase=edificio_id)
    if vivienda_id:
        qs_plan = qs_plan.filter(tarea_obra__legacy_cod_vivienda=vivienda_id)
    if planta_id:
        qs_plan = qs_plan.filter(tarea_obra__legacy_planta=planta_id)
    if empleado_id:
        qs_plan = qs_plan.filter(empleado_id=empleado_id)
    if estado and estado != "HISTORICO":
        qs_plan = qs_plan.filter(estado=estado)
    if estado == "HISTORICO":
        qs_plan = qs_plan.none()

    rows = []

    for a in qs_plan:
        estado_label = a.get_estado_display()
        origen_label = "Portal · Realizado" if a.estado == "REALIZADO" else "Portal · Planificado"
        tarea = getattr(a, "tarea_obra", None)
        partida_fallback = getattr(a, "pi_display_partida", "")
        capitulo_fallback = getattr(a, "pi_display_capitulo", "")
        partida_obj = (
            _safe_related(a, "partida")
            or _safe_related(tarea, "partida")
            or _catalog_find(partidas_catalogo_by_code, partida_fallback)
        )
        capitulo_obj = (
            _safe_related(a, "capitulo")
            or _safe_related(tarea, "capitulo")
            or _safe_related(partida_obj, "capitulo")
            or _catalog_find(capitulos_catalogo_by_code, capitulo_fallback)
            or _catalog_find(capitulos_catalogo_by_code, _capitulo_code_from_partida(partida_fallback))
        )
        partida_info = _catalog_display_final(partida_obj, partida_fallback)
        capitulo_info = _catalog_display_final(capitulo_obj, capitulo_fallback)

        rows.append(SimpleNamespace(
            source_type="asignacion",
            pk=a.pk,
            source_id=a.pk,
            fecha_inicio=a.fecha_inicio,
            fecha_fin=a.fecha_fin,
            hora_inicio=a.hora_inicio,
            hora_fin=a.hora_fin,
            horas="",
            empleado=str_or_dash(a.empleado),
            obra=a.pi_display_obra,
            vivienda=a.pi_display_vivienda_corta,
            planta=a.pi_display_planta,
            capitulo=a.pi_display_capitulo,
            partida=a.pi_display_partida,
            estado=a.estado,
            estado_label=estado_label,
            # ASIGNACIONES_LIST_AVANCE_ACTUAL_V1_1
            avance_actual=(
                getattr(
                    getattr(a, "tarea_obra", None),
                    "porcentaje_completado",
                    None,
                )
                or 0
            ),
            origen_label=origen_label,
            css_estado="realizado" if a.estado == "REALIZADO" else "pendiente",
            editable=True,
        ))

    # ------------------------------------------------------
    # HISTÓRICO REAL LEGACY
    # Solo mano de obra, antes de hoy, no generado por portal.
    # ------------------------------------------------------
    qs_real = TareaRecursoReal.objects.select_related(
        "team",
        "empleado",
        "empleado__rrhh_empleado",
        "tarea_obra",
        "tarea_obra__obra",
        "unidad_obra",
        "partida",
    ).filter(
        empleado__isnull=False,
        tarea_obra__isnull=False,
        inicio_recurso_real__isnull=False,
        inicio_recurso_real__lt=today,
        legacy_tipo_recurso__in=["M.O. ADM.", "PER. CONT.", "M.O. CONT."],
    )

    qs_real = by_team(qs_real)

    # PI_PERSONAL_UNIFIED_REAL_300K_DEDUPE_V3
    # Incluir reales 300000+ creados desde tarea/manual, pero no duplicar
    # el real generado por una AsignacionObra visible.
    portal_real_legacy_ids = {
        300000 + int(pk)
        for pk in qs_plan.values_list("id", flat=True)
    }
    if portal_real_legacy_ids:
        qs_real = qs_real.exclude(legacy_id_recurso_tarea__in=portal_real_legacy_ids)

    # Rendimiento:
    # Si no hay filtro explícito de fechas, no cargamos todo el histórico legacy.
    # Por defecto mostramos solo realizados recientes. Para consultar histórico amplio,
    # usar fecha_desde / fecha_hasta.
    if not (fecha_dt or fecha_desde_dt or fecha_hasta_dt):
        qs_real = qs_real.filter(
            inicio_recurso_real__gte=today - timedelta(days=HISTORICO_REAL_DEFAULT_DAYS)
        )

    if fecha_dt:
        qs_real = qs_real.filter(inicio_recurso_real=fecha_dt)
    if fecha_desde_dt:
        qs_real = qs_real.filter(inicio_recurso_real__gte=fecha_desde_dt)
    if fecha_hasta_dt:
        qs_real = qs_real.filter(inicio_recurso_real__lte=fecha_hasta_dt)
    if obra_id:
        qs_real = qs_real.filter(tarea_obra__obra_id=obra_id)
    if edificio_id:
        qs_real = qs_real.filter(legacy_cod_fase=edificio_id)
    if vivienda_id:
        qs_real = qs_real.filter(legacy_cod_vivienda=vivienda_id)
    if planta_id:
        qs_real = qs_real.filter(legacy_planta=planta_id)
    if empleado_id:
        qs_real = qs_real.filter(empleado__rrhh_empleado_id=empleado_id)
    if estado and estado != "REALIZADO":
        qs_real = qs_real.none()

    for r in qs_real.order_by("-inicio_recurso_real", "-id")[:500]:
        tarea = r.tarea_obra
        obra = getattr(tarea, "obra", None)
        partida_fallback = getattr(r, "legacy_partida", "") or getattr(tarea, "legacy_partida", "")
        capitulo_fallback = getattr(r, "legacy_capitulo", "") or getattr(tarea, "legacy_capitulo", "")
        partida_obj = (
            _safe_related(r, "partida")
            or _safe_related(tarea, "partida")
            or _catalog_find(partidas_catalogo_by_code, partida_fallback)
        )
        capitulo_obj = (
            _safe_related(tarea, "capitulo")
            or _safe_related(partida_obj, "capitulo")
            or _catalog_find(capitulos_catalogo_by_code, capitulo_fallback)
            or _catalog_find(capitulos_catalogo_by_code, _capitulo_code_from_partida(partida_fallback))
        )
        partida_info = _catalog_display_final(partida_obj, partida_fallback)
        capitulo_info = _catalog_display_final(capitulo_obj, capitulo_fallback)

        rows.append(SimpleNamespace(
            source_type="historico",
            pk=r.pk,
            source_id=r.pk,
            fecha_inicio=r.inicio_recurso_real,
            fecha_fin=r.fin_recurso_real or r.inicio_recurso_real,
            hora_inicio=None,
            hora_fin=None,
            horas=r.cantidad,
            empleado=str_or_dash(r.empleado),
            obra=str_or_dash(obra) if obra else str_or_dash(r.legacy_cod_obra),
            vivienda=vivienda_label(r.legacy_cod_vivienda),
            planta=r.legacy_planta or "-",
            capitulo=r.legacy_capitulo or "-",
            partida=getattr(partida_info, "nombre", "") or partida_fallback or "-",
            partida_codigo=getattr(partida_info, "codigo", "") or partida_fallback,
            estado="REALIZADO",
            estado_label="Realizado",
            avance_actual=(
                getattr(
                    getattr(r, "tarea_obra", None),
                    "porcentaje_completado",
                    None,
                )
                or 0
            ),
            origen_label="Realizado",
            css_estado="realizado",
            editable=False,
        ))

    # NORMALIZACIÓN FINAL CATÁLOGOS EN LISTADO
    # Los históricos pueden traer solo códigos legacy; aquí resolvemos nombre real
    # desde PartidaCatalogo.codigo y CapituloCatalogo.codigo.
    def _pi_catalog_key(value):
        value = str(value or "").strip().upper()
        return "".join(ch for ch in value if ch.isalnum())

    def _pi_catalog_aliases(value):
        raw = str(value or "").strip().upper()
        key = _pi_catalog_key(raw)
        aliases = {key} if key else set()

        if key.startswith("C"):
            num = key[1:]
            if num:
                aliases.add(num)
                aliases.add(num.zfill(2))
                try:
                    aliases.add(str(int(num)))
                except Exception:
                    pass

        if key.isdigit():
            aliases.add("C" + key.zfill(2))
            try:
                aliases.add("C" + str(int(key)))
            except Exception:
                pass

        if "." in raw:
            prefix = raw.split(".", 1)[0]
            aliases.update(_pi_catalog_aliases(prefix))

        return {a for a in aliases if a}

    def _pi_build_catalog_by_codigo(model):
        data = {}
        try:
            qs = model.objects.all()
        except Exception:
            return data

        for obj in qs:
            codigo = getattr(obj, "codigo", "") or ""
            for alias in _pi_catalog_aliases(codigo):
                data[alias] = obj
        return data

    def _pi_lookup_catalog(data, *values):
        for value in values:
            for alias in _pi_catalog_aliases(value):
                obj = data.get(alias)
                if obj:
                    return obj
        return None

    def _pi_capitulo_code_from_partida(value):
        value = str(value or "").strip()
        if "." in value:
            prefix = value.split(".", 1)[0]
            try:
                return "C" + str(int(prefix)).zfill(2)
            except Exception:
                return "C" + prefix
        return ""

    partidas_catalogo_final = _pi_build_catalog_by_codigo(PartidaCatalogo)
    capitulos_catalogo_final = _pi_build_catalog_by_codigo(CapituloCatalogo)

    for item in rows:
        partida_raw = getattr(item, "partida_codigo", "") or getattr(item, "partida", "")
        partida_obj = _pi_lookup_catalog(partidas_catalogo_final, partida_raw)

        if partida_obj:
            partida_codigo = getattr(partida_obj, "codigo", "") or partida_raw
            partida_nombre = getattr(partida_obj, "nombre", "") or partida_raw

            item.partida = partida_nombre
            item.partida_codigo = partida_codigo
            item.partida_title = f"{partida_codigo} · {partida_nombre}"

        capitulo_raw = getattr(item, "capitulo_codigo", "") or getattr(item, "capitulo", "")
        capitulo_from_partida = _pi_capitulo_code_from_partida(getattr(item, "partida_codigo", "") or partida_raw)
        capitulo_obj = _pi_lookup_catalog(capitulos_catalogo_final, capitulo_raw, capitulo_from_partida)

        if capitulo_obj:
            capitulo_codigo = getattr(capitulo_obj, "codigo", "") or capitulo_raw
            capitulo_nombre = getattr(capitulo_obj, "nombre", "") or capitulo_raw

            item.capitulo = capitulo_nombre
            item.capitulo_codigo = capitulo_codigo
            item.capitulo_title = f"{capitulo_codigo} · {capitulo_nombre}"


    # Orden descendente por fecha. Si hay hora, también descendente.
    rows.sort(
        key=lambda x: (
            x.fecha_inicio,
            x.hora_inicio or timezone.datetime.min.time(),
            x.source_type,
            x.source_id,
        ),
        reverse=True,
    )

    rows_limitadas = rows[:500]

    obras = by_team(ObraPlanificacion.objects.all()).order_by("codigo", "id")

    # ASIGNACIONES_PRODUCCION_VIVIENDA_OPTIONS_V1
    tareas_opciones_base = by_team(TareaObra.objects.select_related("obra")).filter(obra_id__isnull=False)

    if obra_id:
        tareas_opciones = tareas_opciones_base.filter(obra_id=obra_id)
    else:
        tareas_opciones = tareas_opciones_base.none()

    # ASIGNACIONES_EDIFICIO_FASE_LABEL_NOMBRE_V1
    def _asig_unidad_nombre_edificio(unidad):
        if not unidad:
            return ""
        candidatos = [
            "edificio",
            "fase",
            "nombre_edificio",
            "nombre_fase",
            "descripcion_edificio",
            "descripcion_fase",
            "nombre",
            "descripcion",
            "titulo",
        ]
        for field in candidatos:
            value = getattr(unidad, field, None)
            value = str(value or "").strip()
            if value and value not in {"0", "-"}:
                return value
        return ""

    edificios_map = {}
    for t in (
        tareas_opciones
        .exclude(legacy_cod_fase__isnull=True)
        .select_related("unidad_obra")
        .order_by("legacy_cod_fase", "id")
    ):
        key = str(t.legacy_cod_fase or "").strip()
        if not key:
            continue

        nombre = _asig_unidad_nombre_edificio(getattr(t, "unidad_obra", None))
        if nombre:
            label = f"{key} · {nombre}"
        else:
            label = key

        edificios_map.setdefault(key, label)

    edificios = [
        {"id": key, "label": label}
        for key, label in sorted(
            edificios_map.items(),
            key=lambda item: int(item[0]) if str(item[0]).isdigit() else str(item[0])
        )
    ]

    tareas_vivienda_opts = tareas_opciones
    if edificio_id:
        tareas_vivienda_opts = tareas_vivienda_opts.filter(legacy_cod_fase=edificio_id)

    viviendas = [
        {"id": str(v), "label": str(v)}
        for v in tareas_vivienda_opts.exclude(legacy_cod_vivienda__isnull=True)
        .values_list("legacy_cod_vivienda", flat=True)
        .distinct()
        .order_by("legacy_cod_vivienda")
    ]

    tareas_planta_opts = tareas_vivienda_opts
    if vivienda_id:
        tareas_planta_opts = tareas_planta_opts.filter(legacy_cod_vivienda=vivienda_id)

    plantas = [
        {"id": str(v), "label": str(v)}
        for v in tareas_planta_opts.exclude(legacy_planta__isnull=True)
        .exclude(legacy_planta="")
        .values_list("legacy_planta", flat=True)
        .distinct()
        .order_by("legacy_planta")
    ]

    # ASIGNACIONES_PERSONAL_ESTRUCTURA_JSON_LOCAL_V1
    # Mapa local para cascada inmediata, usando la misma lógica de Planning de Obra:
    # Obra -> legacy_cod_fase -> legacy_cod_vivienda -> legacy_planta.
    estructura_personal = {
        "edificios": [],
        "viviendasByFase": {},
        "plantasByFaseVivienda": {},
    }

    fase_labels = {}
    viviendas_by_fase = {}
    plantas_by_fase_vivienda = {}

    estructura_base = tareas_opciones
    if obra_id:
        estructura_base = estructura_base.select_related("unidad_obra").order_by(
            "legacy_cod_fase",
            "legacy_cod_vivienda",
            "legacy_planta",
            "id",
        )

        for t_est in estructura_base:
            fase_code = str(getattr(t_est, "legacy_cod_fase", "") or "").strip()
            viv_code = str(getattr(t_est, "legacy_cod_vivienda", "") or "").strip()
            planta_code = str(getattr(t_est, "legacy_planta", "") or "").strip()

            if not fase_code:
                continue

            unidad = getattr(t_est, "unidad_obra", None)
            fase_nombre = _asig_unidad_nombre_edificio(unidad) if "_asig_unidad_nombre_edificio" in locals() else ""
            fase_label = f"{fase_code} · {fase_nombre}" if fase_nombre else fase_code
            fase_labels.setdefault(fase_code, fase_label)

            if viv_code:
                viviendas_by_fase.setdefault(fase_code, set()).add(viv_code)

            if viv_code and planta_code:
                plantas_by_fase_vivienda.setdefault(f"{fase_code}::{viv_code}", set()).add(planta_code)

    def _asig_sort_key(value):
        value = str(value or "")
        try:
            return (0, int(value))
        except Exception:
            return (1, value)

    estructura_personal["edificios"] = [
        {"id": code, "label": label}
        for code, label in sorted(fase_labels.items(), key=lambda item: _asig_sort_key(item[0]))
    ]

    estructura_personal["viviendasByFase"] = {
        fase_code: [
            {"id": viv, "label": f"Viv. {viv}" if viv not in {"0", "OBRA", "Obra"} else "Obra"}
            for viv in sorted(vivs, key=_asig_sort_key)
        ]
        for fase_code, vivs in viviendas_by_fase.items()
    }

    estructura_personal["plantasByFaseVivienda"] = {
        key: [
            {"id": planta, "label": planta}
            for planta in sorted(plantas_set, key=_asig_sort_key)
        ]
        for key, plantas_set in plantas_by_fase_vivienda.items()
    }

    estructura_personal_json = json.dumps(estructura_personal, ensure_ascii=False)

    # Selector de empleados: solo personal activo/planificable.
    # No debe cargar históricos de asignaciones, porque aparecen bajas/antiguos.
    empleados = AsignacionObraForm().fields["empleado"].queryset


    estado_choices = [
        ("PENDIENTE", "Pendiente"),
        ("REALIZADO", "Realizado"),
    ]


    # FINAL LISTADO PERSONAL: horas, importe y partida desde FK real.
    # Se aplica justo antes del render para pisar normalizaciones legacy anteriores.
    from decimal import Decimal, ROUND_HALF_UP
    from datetime import datetime
    from django.apps import apps

    TareaRecursoRealFinal = apps.get_model("planificacion_obra", "TareaRecursoReal")
    AsignacionObraFinal = apps.get_model("planificacion_obra", "AsignacionObra")
    EmpleadoObraFinal = apps.get_model("planificacion_obra", "EmpleadoObra")

    def _pf_decimal(value):
        try:
            return Decimal(str(value or 0))
        except Exception:
            return Decimal("0")

    def _pf_fmt(value, decimals=2, suffix=""):
        q = Decimal("1").scaleb(-decimals)
        val = _pf_decimal(value).quantize(q, rounding=ROUND_HALF_UP)
        txt = f"{val:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{txt}{suffix}"

    def _pf_catalog_label(obj, fallback=""):
        codigo = str(getattr(obj, "codigo", "") or "").strip()
        nombre = str(getattr(obj, "nombre", "") or "").strip()
        fallback = str(fallback or "").strip()
        if codigo and nombre:
            return codigo, nombre, f"{codigo} · {nombre}"
        label = nombre or codigo or fallback or "-"
        return codigo or fallback, label, label

    def _pf_horas_desde_item(item):
        fecha_inicio = getattr(item, "fecha_inicio", None)
        fecha_fin = getattr(item, "fecha_fin", None) or fecha_inicio
        hora_inicio = getattr(item, "hora_inicio", None)
        hora_fin = getattr(item, "hora_fin", None)

        if fecha_inicio and fecha_fin and hora_inicio and hora_fin:
            try:
                inicio = datetime.combine(fecha_inicio, hora_inicio)
                fin = datetime.combine(fecha_fin, hora_fin)
                if fin > inicio:
                    return (Decimal(str((fin - inicio).total_seconds())) / Decimal("3600")).quantize(Decimal("0.0001"))
            except Exception:
                pass

        return _pf_decimal(getattr(item, "horas", 0))

    historico_ids_final = [
        getattr(item, "source_id", None) or getattr(item, "pk", None)
        for item in rows
        if getattr(item, "source_type", "") == "historico" and (getattr(item, "source_id", None) or getattr(item, "pk", None))
    ]

    asignacion_ids_final = [
        getattr(item, "source_id", None) or getattr(item, "pk", None)
        for item in rows
        if getattr(item, "source_type", "") != "historico" and (getattr(item, "source_id", None) or getattr(item, "pk", None))
    ]

    reales_final = {
        r.id: r
        for r in TareaRecursoRealFinal.objects.filter(id__in=historico_ids_final).select_related(
            "partida",
            "partida__capitulo",
            "tarea_obra",
            "tarea_obra__partida",
            "tarea_obra__partida__capitulo",
            "tarea_obra__capitulo",
            "empleado",
        )
    }

    asignaciones_final = {
        a.id: a
        for a in AsignacionObraFinal.objects.filter(id__in=asignacion_ids_final).select_related(
            "team",
            "empleado",
            "partida",
            "partida__capitulo",
            "capitulo",
            "tarea_obra",
            "tarea_obra__partida",
            "tarea_obra__partida__capitulo",
            "tarea_obra__capitulo",
        )
    }

    precio_por_asignacion = {}
    if asignaciones_final:
        empleado_ids = [a.empleado_id for a in asignaciones_final.values() if a.empleado_id]
        team_ids = [a.team_id for a in asignaciones_final.values() if a.team_id]
        for eo in (
            EmpleadoObraFinal.objects
            .filter(rrhh_empleado_id__in=empleado_ids, team_id__in=team_ids)
            .order_by("team_id", "rrhh_empleado_id", "-id")
        ):
            key = (eo.team_id, eo.rrhh_empleado_id)
            if key not in precio_por_asignacion:
                precio_por_asignacion[key] = _pf_decimal(eo.precio_hora)

    for item in rows:
        horas = Decimal("0")
        precio = Decimal("0")
        importe = Decimal("0")

        item_id = getattr(item, "source_id", None) or getattr(item, "pk", None)

        if getattr(item, "source_type", "") == "historico":
            real = reales_final.get(item_id)
            if real:
                partida_obj = (
                    getattr(real, "partida", None)
                    or getattr(getattr(real, "tarea_obra", None), "partida", None)
                )
                capitulo_obj = (
                    getattr(partida_obj, "capitulo", None)
                    or getattr(getattr(real, "tarea_obra", None), "capitulo", None)
                )

                cap_code, cap_name, cap_title = _pf_catalog_label(capitulo_obj, getattr(real, "legacy_capitulo", ""))
                par_code, par_name, par_title = _pf_catalog_label(partida_obj, getattr(real, "legacy_partida", ""))

                item.capitulo = cap_name
                item.capitulo_codigo = cap_code
                item.capitulo_title = cap_title
                item.partida = par_name
                item.partida_codigo = par_code
                item.partida_title = par_title

                horas = _pf_decimal(getattr(real, "cantidad", None) or getattr(real, "horas_reales", None) or getattr(real, "horas", None))
                precio = _pf_decimal(getattr(real, "precio_unidad", None))
                importe = _pf_decimal(getattr(real, "costo_recurso_real", None))
                if not importe:
                    importe = horas * precio
            else:
                horas = _pf_decimal(getattr(item, "horas", 0))

        else:
            asignacion = asignaciones_final.get(item_id)
            horas = _pf_horas_desde_item(item)

            if asignacion:
                precio = precio_por_asignacion.get((asignacion.team_id, asignacion.empleado_id), Decimal("0"))
                importe = horas * precio

                partida_obj = (
                    getattr(asignacion, "partida", None)
                    or getattr(getattr(asignacion, "tarea_obra", None), "partida", None)
                )
                capitulo_obj = (
                    getattr(asignacion, "capitulo", None)
                    or getattr(partida_obj, "capitulo", None)
                    or getattr(getattr(asignacion, "tarea_obra", None), "capitulo", None)
                )

                cap_code, cap_name, cap_title = _pf_catalog_label(capitulo_obj, getattr(item, "capitulo", ""))
                par_code, par_name, par_title = _pf_catalog_label(partida_obj, getattr(item, "partida", ""))

                item.capitulo = cap_name
                item.capitulo_codigo = cap_code
                item.capitulo_title = cap_title
                item.partida = par_name
                item.partida_codigo = par_code
                item.partida_title = par_title

        item.horas_decimal = horas
        item.precio_hora_decimal = precio
        item.importe_decimal = importe
        item.horas_display = _pf_fmt(horas, 1, " h")
        item.importe_display = _pf_fmt(importe, 2, " €")



    # ASIGNACIONES_LIST_EMPLEADOOBRA_NOMBRE_V1
    # En filas Portal/AsignacionObra, el FK empleado apunta a RRHH. Para mostrar en obra
    # se debe usar EmpleadoObra.nombre asociado por rrhh_empleado_id y team.
    try:
        portal_ids = [
            getattr(item, "pk", None)
            for item in rows_limitadas
            if getattr(item, "editable", False) and getattr(item, "pk", None)
        ]

        if portal_ids:
            asignaciones_portal = {
                a.id: a
                for a in AsignacionObraFinal.objects
                .filter(id__in=portal_ids)
                .select_related("team", "empleado")
            }

            rrhh_ids = [
                a.empleado_id
                for a in asignaciones_portal.values()
                if getattr(a, "empleado_id", None)
            ]

            team_ids = [
                a.team_id
                for a in asignaciones_portal.values()
                if getattr(a, "team_id", None)
            ]

            empleados_obra = (
                EmpleadoObraFinal.objects
                .filter(rrhh_empleado_id__in=rrhh_ids)
                .filter(team_id__in=team_ids)
                .order_by("rrhh_empleado_id", "team_id", "-id")
            )

            empleado_obra_por_rrhh_team = {}
            empleado_obra_por_rrhh = {}

            for eo in empleados_obra:
                if not getattr(eo, "nombre", None):
                    continue

                key_team = (eo.rrhh_empleado_id, eo.team_id)
                empleado_obra_por_rrhh_team.setdefault(key_team, eo.nombre)
                empleado_obra_por_rrhh.setdefault(eo.rrhh_empleado_id, eo.nombre)

            for item in rows_limitadas:
                if not getattr(item, "editable", False):
                    continue

                asignacion = asignaciones_portal.get(getattr(item, "pk", None))
                if not asignacion or not getattr(asignacion, "empleado_id", None):
                    continue

                nombre_obra = (
                    empleado_obra_por_rrhh_team.get((asignacion.empleado_id, asignacion.team_id))
                    or empleado_obra_por_rrhh.get(asignacion.empleado_id)
                )

                if nombre_obra:
                    item.empleado = nombre_obra
                    item.empleado_display = nombre_obra
                    item.empleado_nombre_obra = nombre_obra

    except Exception:
        # No romper el listado por un ajuste visual de nombres.
        pass


    context = {
        "asignaciones": rows_limitadas,
        "asignaciones_count": len(rows),
        "total_asignaciones": len(rows),
        "total_mostradas": len(rows_limitadas),
        "obras": obras,
        "empleados": empleados,
        "edificios": edificios,
        "viviendas": viviendas,
        "plantas": plantas,
        "estructura_personal_json": estructura_personal,
        "estado_choices": estado_choices,
        "filtros": {
            "fecha": fecha,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "obra": obra_id,
            "edificio": edificio_id,
            "fase": edificio_id,
            "vivienda": vivienda_id,
            "planta": planta_id,
            "empleado": empleado_id,
            "estado": estado,
        },
    }

    return render(request, "planificacion_obra/asignaciones_list.html", context)


def _pi_get_team_for_asignacion(request, asignacion=None):
    """
    Team obligatorio para AsignacionObra.

    Prioridad:
    1) team de la tarea_obra
    2) active_team_id numérico de sesión si pertenece al usuario
    3) primer team del usuario

    Nota:
    active_team_id puede venir como "all" desde el selector global.
    En ese caso NO debe usarse como pk.
    """
    tarea = getattr(asignacion, "tarea_obra", None)

    if tarea and getattr(tarea, "team_id", None):
        return tarea.team

    user = getattr(request, "user", None)

    if not user or not hasattr(user, "teams"):
        return None

    teams = user.teams.all()

    active_team_id = request.session.get("active_team_id")

    if active_team_id and str(active_team_id).isdigit():
        team = teams.filter(pk=int(active_team_id)).first()
        if team:
            return team

    return teams.first()


# ASIGNACION_EMPLEADOS_OPTIONS_JSON_V1
def _planificacion_empleado_options_json(form):
    import json
    from django.apps import apps

    EmpleadoObra = apps.get_model("planificacion_obra", "EmpleadoObra")

    try:
        qs = form.fields["empleado"].queryset
    except Exception:
        qs = []

    ids = list(qs.values_list("id", flat=True)) if hasattr(qs, "values_list") else [
        getattr(e, "id", None) for e in qs
    ]

    labels_by_rrhh = {}
    eo_qs = (
        EmpleadoObra.objects
        .exclude(rrhh_empleado_id__isnull=True)
        .filter(
            rrhh_empleado_id__in=ids,
            tipo=EmpleadoObra.Tipo.ADMINISTRADA,
            situacion=EmpleadoObra.Situacion.ACTIVO,
            fecha_baja__isnull=True,
        )
        .order_by("rrhh_empleado_id", "-id")
    )

    for eo in eo_qs:
        key = int(eo.rrhh_empleado_id)
        if key not in labels_by_rrhh:
            labels_by_rrhh[key] = eo.nombre or ""

    options = []
    for empleado in qs:
        label = (
            labels_by_rrhh.get(int(empleado.pk))
            or getattr(empleado, "nombre_completo", None)
            or getattr(empleado, "nombre", None)
            or str(empleado)
        )
        options.append({
            "id": empleado.pk,
            "text": str(label),
        })

    return json.dumps(options, ensure_ascii=False)

def _planificacion_empleado_precios_json():
    import json
    from decimal import Decimal
    from django.apps import apps

    EmpleadoObra = apps.get_model("planificacion_obra", "EmpleadoObra")

    precios = {}
    qs = (
        EmpleadoObra.objects
        .exclude(rrhh_empleado_id__isnull=True)
        .filter(
            tipo=EmpleadoObra.Tipo.ADMINISTRADA,
            situacion=EmpleadoObra.Situacion.ACTIVO,
            fecha_baja__isnull=True,
        )
        .order_by("rrhh_empleado_id", "-id")
    )

    for eo in qs:
        key = str(eo.rrhh_empleado_id)
        if key in precios:
            continue
        precio = eo.precio_hora
        if precio is None:
            precio = Decimal("0")
        precios[key] = {
            "precio_hora": float(precio),
            "empleado_obra_id": eo.id,
            "nombre": eo.nombre or "",
        }

    return json.dumps(precios, ensure_ascii=False)

def _asignacion_fin_datetime_aware(asignacion):
    from datetime import datetime
    from django.utils import timezone

    if not getattr(asignacion, "fecha_fin", None) or not getattr(asignacion, "hora_fin", None):
        return None

    fin_dt = datetime.combine(asignacion.fecha_fin, asignacion.hora_fin)

    if timezone.is_naive(fin_dt):
        fin_dt = timezone.make_aware(fin_dt, timezone.get_current_timezone())

    return fin_dt


def _asignacion_borrar_real_portal_generado(asignacion):
    if not getattr(asignacion, "pk", None):
        return 0

    from .models import TareaRecursoReal
    from .services_realizacion import legacy_id_recurso_tarea_for_asignacion

    legacy_id = legacy_id_recurso_tarea_for_asignacion(asignacion)

    deleted, _ = (
        TareaRecursoReal.objects
        .filter(team_id=asignacion.team_id, legacy_id_recurso_tarea=legacy_id)
        .delete()
    )

    return deleted


def _asignacion_recurso_real_portal_ids(
    asignacion,
):
    if not getattr(
        asignacion,
        "pk",
        None,
    ):
        return []

    from .models import TareaRecursoReal
    from .services_realizacion import (
        legacy_id_recurso_tarea_for_asignacion,
    )

    legacy_id = (
        legacy_id_recurso_tarea_for_asignacion(
            asignacion
        )
    )

    return list(
        TareaRecursoReal.objects
        .filter(
            team_id=asignacion.team_id,
            legacy_id_recurso_tarea=legacy_id,
        )
        .order_by("pk")
        .values_list(
            "pk",
            flat=True,
        )
    )



def _asignacion_guardar_y_sincronizar_estado(asignacion, user=None):
    """
    Regla operativa:
    - Si fecha/hora fin es futura y viene REALIZADO, se fuerza a PENDIENTE.
    - Si queda REALIZADO, se crea/actualiza TareaRecursoReal.
    - Si queda PENDIENTE, se elimina el real portal asociado si existía.
    """
    from django.utils import timezone
    from .models import AsignacionObra
    from .services_realizacion import realizar_asignacion_obra, RealizacionAsignacionError

    fin_dt = _asignacion_fin_datetime_aware(asignacion)
    now = timezone.now()

    if fin_dt and fin_dt > now and asignacion.estado == AsignacionObra.Estado.REALIZADO:
        asignacion.estado = AsignacionObra.Estado.PENDIENTE
        asignacion.save()
        _asignacion_borrar_real_portal_generado(asignacion)
        return "pendiente_forzada", "La fecha/hora fin es futura; la asignación se dejó pendiente."

    asignacion.save()

    if asignacion.estado == AsignacionObra.Estado.REALIZADO:
        try:
            realizar_asignacion_obra(asignacion, user=user)
        except RealizacionAsignacionError as exc:
            asignacion.estado = AsignacionObra.Estado.PENDIENTE
            asignacion.save(update_fields=["estado", "actualizado_en"])
            _asignacion_borrar_real_portal_generado(asignacion)
            return "error", str(exc)

        return "realizado", "Asignación guardada como realizada y parte de trabajo actualizado."

    _asignacion_borrar_real_portal_generado(asignacion)
    return "pendiente", "Asignación guardada como pendiente."

def asignacion_create(request):
    initial = {}
    for key in [
        "empleado",
        "obra",
        "fase",
        "vivienda",
        "nivel",
        "planta_trabajo",
        "capitulo",
        "partida",
        "tarea_obra",
        "fecha_inicio",
        "hora_inicio",
        "fecha_fin",
        "hora_fin",
        "estado",
        "observaciones",
    ]:
        value = request.GET.get(key)
        if value:
            initial[key] = value

    if request.method == "POST":
        form = AsignacionObraForm(request.POST, request_user=request.user)
        if form.is_valid():
            asignacion = form.save(commit=False)

            if getattr(asignacion, "team_id", None) is None:
                asignacion.team = _pi_get_team_for_asignacion(request, asignacion)

            if asignacion.team_id is None:
                form.add_error(None, "No se pudo determinar la empresa/equipo activo para esta asignación.")
                return render(request, "planificacion_obra/asignacion_form.html", {"form": form})

            asignacion.creado_por = request.user
            operation_id = _tm_uuid4().hex

            with transaction.atomic():
                # ASIGNACION_APLICAR_AVANCE_ASIGNACION_CREATE_V1_1
                _asignacion_aplicar_avance_tarea(
                    form=form,
                    asignacion=asignacion,
                )

                estado_sync, estado_msg = (
                    _asignacion_guardar_y_sincronizar_estado(
                        asignacion,
                        user=request.user,
                    )
                )

                recurso_real_ids = (
                    _asignacion_recurso_real_portal_ids(
                        asignacion
                    )
                )

                registrar_creacion_asignacion(
                    asignacion=asignacion,
                    actor=request.user,
                    fuente="formulario",
                    operation_id=operation_id,
                    recurso_real_ids=(
                        recurso_real_ids
                    ),
                    estado_sync=estado_sync,
                )

            if estado_sync == "realizado":
                messages.success(request, estado_msg)
            elif estado_sync == "pendiente_forzada":
                messages.warning(request, estado_msg)
            elif estado_sync == "pendiente":
                messages.success(request, estado_msg)
            else:
                messages.error(request, estado_msg or "No se pudo sincronizar la asignación.")

            return redirect("planificacion_obra:asignaciones_list")
    else:
        form = AsignacionObraForm(request_user=request.user, initial=initial)

    context = {
        "form": form,
        "empleado_precios_json": _planificacion_empleado_precios_json(),
        "titulo": "Nueva asignación de personal",
    }
    return render(request, "planificacion_obra/asignacion_form.html", context)



@login_required
def asignacion_repetir(request, pk):
    from django.shortcuts import get_object_or_404, redirect, render
    from django.contrib import messages
    from .models import AsignacionObra
    from .forms import AsignacionObraForm

    qs = AsignacionObra.objects.select_related(
        "team",
        "empleado",
        "tarea_obra",
        "tarea_obra__obra",
        "unidad_obra",
        "unidad_obra__obra",
        "capitulo",
        "partida",
    )

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs = qs.filter(team__in=request.user.teams.all())

    origen = get_object_or_404(qs, pk=pk)

    obra_id = None
    if getattr(origen, "tarea_obra_id", None) and getattr(origen.tarea_obra, "obra_id", None):
        obra_id = origen.tarea_obra.obra_id
    elif getattr(origen, "unidad_obra_id", None) and getattr(origen.unidad_obra, "obra_id", None):
        obra_id = origen.unidad_obra.obra_id

    # Repetir debe copiar toda la estructura operativa.
    # El formulario depende de la cadena:
    # obra -> fase/edificio -> vivienda -> planta -> capítulo -> partida -> tarea.
    # Si no precargamos fase/planta correctamente, los selects dependientes quedan vacíos.
    unidad_origen = getattr(origen, "unidad_obra", None)
    tarea_origen = getattr(origen, "tarea_obra", None)

    fase_origen = ""
    if unidad_origen is not None:
        try:
            from .forms import unit_text_field_names, value_as_text
            fase_fields = unit_text_field_names()
            fase_origen = value_as_text(unidad_origen, fase_fields) or ""
        except Exception:
            fase_origen = ""

        if not fase_origen:
            for attr in [
                "fase",
                "edificio",
                "edificio_fase",
                "bloque",
                "portal",
                "zona",
                "legacy_fase",
                "legacy_edificio",
            ]:
                value = getattr(unidad_origen, attr, None)
                if value not in ("", None):
                    fase_origen = str(value)
                    break

    planta_origen = (
        getattr(origen, "planta_trabajo", None)
        or getattr(tarea_origen, "legacy_planta", None)
        or getattr(unidad_origen, "planta", None)
        or getattr(unidad_origen, "legacy_planta", None)
        or ""
    )

    initial = {
        "empleado": origen.empleado_id,
        "obra": obra_id,
        "fase": fase_origen,
        "vivienda": origen.unidad_obra_id,
        "unidad_obra": origen.unidad_obra_id,
        "planta_trabajo": planta_origen,
        "capitulo": origen.capitulo_id,
        "partida": origen.partida_id,
        "tarea_obra": origen.tarea_obra_id,
        "fecha_inicio": origen.fecha_inicio,
        "hora_inicio": origen.hora_inicio,
        "fecha_fin": origen.fecha_fin,
        "hora_fin": origen.hora_fin,
        "estado": origen.estado,
        "observaciones": origen.observaciones,
    }

    def build_context(form):
        return {
            "form": form,
            "empleado_precios_json": _planificacion_empleado_precios_json(),
            "modo_repetir": True,
            "asignacion_origen": origen,
            "titulo": "Repetir asignación de personal",
        }

    if request.method == "POST":
        form = AsignacionObraForm(request.POST, request_user=request.user)
        if form.is_valid():
            nueva = form.save(commit=False)

            if getattr(nueva, "team_id", None) is None:
                nueva.team = origen.team or _pi_get_team_for_asignacion(request, nueva)

            if nueva.team_id is None:
                form.add_error(None, "No se pudo determinar la empresa/equipo activo para esta asignación.")
                return render(request, "planificacion_obra/asignacion_form.html", build_context(form))

            nueva.creado_por = request.user
            operation_id = _tm_uuid4().hex

            with transaction.atomic():
                estado_sync, estado_msg = (
                    _asignacion_guardar_y_sincronizar_estado(
                        nueva,
                        user=request.user,
                    )
                )

                recurso_real_ids = (
                    _asignacion_recurso_real_portal_ids(
                        nueva
                    )
                )

                registrar_repeticion_asignaciones(
                    asignaciones=[
                        nueva,
                    ],
                    actor=request.user,
                    asignacion_origen_id=(
                        origen.pk
                    ),
                    fuente="repetir",
                    operation_id=operation_id,
                    recurso_real_ids=(
                        recurso_real_ids
                    ),
                    estado_sync=estado_sync,
                )

            if estado_sync == "realizado":
                messages.success(request, estado_msg)
            elif estado_sync == "pendiente_forzada":
                messages.warning(request, estado_msg)
            elif estado_sync == "pendiente":
                messages.success(request, estado_msg)
            else:
                messages.error(request, estado_msg or "No se pudo sincronizar la asignación.")

            return redirect("planificacion_obra:asignaciones_list")
    else:
        # En modo repetir usamos instance=origen solo para renderizar el GET.
        # Así AsignacionObraForm reconstruye correctamente los choices dependientes:
        # fase/edificio, vivienda, planta, capítulo, partida y tarea.
        # En POST se sigue usando un form sin instance para crear una asignación nueva.
        form = AsignacionObraForm(instance=origen, request_user=request.user, initial=initial)

    return render(request, "planificacion_obra/asignacion_form.html", build_context(form))

@login_required
def asignacion_estructura_options(request):
    obra_id = request.GET.get("obra") or ""
    fase_id = request.GET.get("fase") or ""
    vivienda = request.GET.get("vivienda") or ""
    nivel = request.GET.get("nivel") or ""
    planta_trabajo = request.GET.get("planta_trabajo") or ""
    capitulo_id = request.GET.get("capitulo") or ""
    partida_id = request.GET.get("partida") or ""

    data = {
        "fases": [],
        "viviendas": [],
        "plantas_trabajo": [],
        "capitulos": [],
        "partidas": [],
        "tareas": [],
    }

    if not obra_id:
        return JsonResponse(data)

    obra = (
        filter_by_active_team(ObraPlanificacion.objects.all(), request)
        .filter(pk=obra_id)
        .first()
    )

    if not obra:
        return JsonResponse(data, status=404)

    fases = (
        FaseObra.objects
        .filter(team=obra.team, obra=obra)
        .order_by("legacy_cod_fase", "nombre")
    )

    data["fases"] = [
        {
            "id": f.id,
            "text": f"{f.legacy_cod_fase} · {f.nombre}",
        }
        for f in fases
    ]

    unidades = UnidadObra.objects.filter(team=obra.team, obra=obra)

    if fase_id:
        unidades = unidades.filter(fase_id=fase_id)

    data["viviendas"] = [
        {"id": v, "text": v}
        for v in (
            unidades
            .exclude(vivienda="")
            .values_list("vivienda", flat=True)
            .distinct()
            .order_by("vivienda")
        )
    ]

    if vivienda:
        unidades = unidades.filter(vivienda=vivienda)

    if nivel:
        unidades = unidades.filter(nivel=nivel)

    tareas = (
        TareaObra.objects
        .filter(team=obra.team, obra=obra)
        .select_related("unidad_obra", "capitulo", "partida")
        .order_by("legacy_cod_fase", "legacy_cod_vivienda", "inicio_tarea", "legacy_orden")
    )

    if fase_id:
        fase = FaseObra.objects.filter(pk=fase_id, obra=obra).first()
        if fase:
            tareas = tareas.filter(legacy_cod_fase=fase.legacy_cod_fase)

    if vivienda:
        tareas = tareas.filter(unidad_obra__vivienda=vivienda)

    if nivel:
        tareas = tareas.filter(unidad_obra__nivel=nivel)

    plantas = (
        tareas
        .exclude(legacy_planta="")
        .values_list("legacy_planta", flat=True)
        .distinct()
        .order_by("legacy_planta")
    )

    data["plantas_trabajo"] = [
        {"id": p, "text": p}
        for p in plantas
    ]

    if planta_trabajo:
        tareas = tareas.filter(legacy_planta=planta_trabajo)

    capitulos = (
        CapituloCatalogo.objects
        .filter(team=obra.team, tareas__in=tareas)
        .distinct()
        .order_by("codigo", "nombre")
    )

    data["capitulos"] = [
        {
            "id": c.id,
            "text": f"{c.codigo} · {c.nombre}" if c.codigo else c.nombre,
        }
        for c in capitulos
    ]

    if capitulo_id:
        tareas = tareas.filter(capitulo_id=capitulo_id)

    partidas = (
        PartidaCatalogo.objects
        .filter(team=obra.team, tareas__in=tareas)
        .distinct()
        .order_by("codigo", "nombre")
    )

    data["partidas"] = [
        {
            "id": p.id,
            "text": f"{p.codigo} · {p.nombre}" if p.codigo else p.nombre,
        }
        for p in partidas
    ]

    if partida_id:
        tareas = tareas.filter(partida_id=partida_id)

    def label_tarea(t):
        unidad = t.unidad_obra
        if unidad:
            unidad_txt = f"{unidad.edificio} · Viv. {unidad.vivienda} · {unidad.nivel}"
        else:
            unidad_txt = f"Viv. {t.legacy_cod_vivienda}"

        planta = t.legacy_planta or "Sin planta"
        cap = t.capitulo.nombre if t.capitulo else t.legacy_capitulo
        par = t.partida.nombre if t.partida else t.legacy_partida
        return f"{unidad_txt} · {planta} · {cap} · {par}"

    data["tareas"] = [
        {
            "id": t.id,
            "text": label_tarea(t),
        }
        for t in tareas[:500]
    ]

    return JsonResponse(data)



# ---------------------------------------------------------------------
# FIX PLANIFICACION OBRA:
# Endpoint JSON sin nivel. Planta = TareaObra.legacy_planta.
# ---------------------------------------------------------------------
def _nivel_fix_filter_if_model_field(qs, field_name, value):
    if not value:
        return qs
    model_fields = {f.name for f in qs.model._meta.get_fields()}
    if field_name in model_fields:
        return qs.filter(**{f"{field_name}_id": value})
    return qs


def asignacion_opciones(request):
    from django.apps import apps
    from django.http import JsonResponse

    TareaObra = apps.get_model("planificacion_obra", "TareaObra")

    obra_id = request.GET.get("obra") or None
    fase_id = request.GET.get("fase") or None
    unidad_id = request.GET.get("unidad") or request.GET.get("unidad_obra") or None
    planta_trabajo = request.GET.get("planta_trabajo") or None
    capitulo_id = request.GET.get("capitulo") or request.GET.get("capitulo_obra") or None
    partida_id = request.GET.get("partida") or request.GET.get("partida_obra") or None

    qs = TareaObra.objects.all()

    # Filtros operativos. NO se usa UnidadObra.nivel.
    qs = _nivel_fix_filter_if_model_field(qs, "obra", obra_id)
    qs = _nivel_fix_filter_if_model_field(qs, "fase", fase_id)
    qs = _nivel_fix_filter_if_model_field(qs, "edificio_fase", fase_id)
    qs = _nivel_fix_filter_if_model_field(qs, "unidad", unidad_id)
    qs = _nivel_fix_filter_if_model_field(qs, "unidad_obra", unidad_id)

    qs_base = qs

    plantas_trabajo = list(
        qs_base.exclude(legacy_planta__isnull=True)
        .exclude(legacy_planta="")
        .order_by("legacy_planta")
        .values_list("legacy_planta", flat=True)
        .distinct()
    )

    if planta_trabajo:
        qs = qs.filter(legacy_planta=planta_trabajo)

    def related_options(qs, tarea_field):
        model_fields = {f.name for f in TareaObra._meta.get_fields()}
        if tarea_field not in model_fields:
            return []

        rel_field = TareaObra._meta.get_field(tarea_field)
        rel_model = rel_field.remote_field.model

        ids = qs.exclude(**{f"{tarea_field}_id__isnull": True}).values_list(f"{tarea_field}_id", flat=True)
        rows = rel_model.objects.filter(pk__in=ids).distinct()

        data = []
        for obj in rows:
            data.append({
                "id": obj.pk,
                "text": str(obj),
            })
        return data

    capitulos = related_options(qs, "capitulo") or related_options(qs, "capitulo_obra")

    qs_partidas = qs
    qs_partidas = _nivel_fix_filter_if_model_field(qs_partidas, "capitulo", capitulo_id)
    qs_partidas = _nivel_fix_filter_if_model_field(qs_partidas, "capitulo_obra", capitulo_id)

    partidas = related_options(qs_partidas, "partida") or related_options(qs_partidas, "partida_obra")

    qs_tareas = qs_partidas
    qs_tareas = _nivel_fix_filter_if_model_field(qs_tareas, "partida", partida_id)
    qs_tareas = _nivel_fix_filter_if_model_field(qs_tareas, "partida_obra", partida_id)

    tareas = [
        {"id": t.pk, "text": str(t)}
        for t in qs_tareas.distinct()[:500]
    ]

    return JsonResponse({
        "plantas_trabajo": [{"id": p, "text": p} for p in plantas_trabajo],
        "capitulos": capitulos,
        "partidas": partidas,
        "tareas": tareas,
    })



# ---------------------------------------------------------------------
# Endpoint real sin nivel.
# Planta = TareaObra.legacy_planta.
# ---------------------------------------------------------------------
def _pi_real_fk_names_to_model(tarea_model, model):
    from django.db.models import ForeignKey

    names = []
    for f in tarea_model._meta.fields:
        if isinstance(f, ForeignKey) and f.remote_field and f.remote_field.model == model:
            names.append(f.name)
    return names


def _pi_real_filter_by_form_field(qs, form, form_names, value):
    from django.db.models import Q

    if not value:
        return qs

    field_model = None
    for name in form_names:
        field = form.fields.get(name)
        if getattr(field, "queryset", None) is not None:
            field_model = field.queryset.model
            break

    if not field_model:
        return qs

    fk_names = _pi_real_fk_names_to_model(qs.model, field_model)
    if not fk_names:
        return qs

    q = Q()
    for fk in fk_names:
        q |= Q(**{f"{fk}_id": value})

    return qs.filter(q)


def _pi_real_related_options(qs, form, form_names):
    field_model = None
    for name in form_names:
        field = form.fields.get(name)
        if getattr(field, "queryset", None) is not None:
            field_model = field.queryset.model
            break

    if not field_model:
        return []

    fk_names = _pi_real_fk_names_to_model(qs.model, field_model)
    if not fk_names:
        return []

    ids = []
    for fk in fk_names:
        ids.extend(
            list(
                qs.exclude(**{f"{fk}_id__isnull": True})
                .values_list(f"{fk}_id", flat=True)
            )
        )

    return [
        {"id": obj.pk, "text": str(obj)}
        for obj in field_model.objects.filter(pk__in=set(ids)).distinct()
    ]


def asignacion_opciones(request):
    from django.apps import apps
    from django.http import JsonResponse
    from planificacion_obra.forms import AsignacionObraForm

    TareaObra = apps.get_model("planificacion_obra", "TareaObra")

    form = AsignacionObraForm()

    obra_id = request.GET.get("obra") or None
    fase_id = request.GET.get("fase") or request.GET.get("edificio_fase") or None
    unidad_id = request.GET.get("unidad") or request.GET.get("unidad_obra") or request.GET.get("vivienda") or None
    planta = request.GET.get("planta_trabajo") or None
    capitulo_id = request.GET.get("capitulo") or request.GET.get("capitulo_obra") or None
    partida_id = request.GET.get("partida") or request.GET.get("partida_obra") or None

    qs = TareaObra.objects.all()

    # NO usar nivel. Solo estructura operativa.
    qs = _pi_real_filter_by_form_field(qs, form, ("obra",), obra_id)
    qs = _pi_real_filter_by_form_field(qs, form, ("fase", "edificio_fase"), fase_id)
    qs = _pi_real_filter_by_form_field(qs, form, ("unidad", "unidad_obra", "vivienda"), unidad_id)

    plantas_qs = qs

    plantas = list(
        plantas_qs.exclude(legacy_planta__isnull=True)
        .exclude(legacy_planta="")
        .order_by("legacy_planta")
        .values_list("legacy_planta", flat=True)
        .distinct()
    )

    if planta:
        qs = qs.filter(legacy_planta=planta)

    capitulos = _pi_real_related_options(qs, form, ("capitulo", "capitulo_obra"))

    qs_partidas = _pi_real_filter_by_form_field(qs, form, ("capitulo", "capitulo_obra"), capitulo_id)
    partidas = _pi_real_related_options(qs_partidas, form, ("partida", "partida_obra"))

    qs_tareas = _pi_real_filter_by_form_field(qs_partidas, form, ("partida", "partida_obra"), partida_id)

    tareas = [
        {"id": t.pk, "text": str(t)}
        for t in qs_tareas.distinct()[:500]
    ]

    return JsonResponse({
        "plantas_trabajo": [{"id": p, "text": p} for p in plantas],
        "capitulos": capitulos,
        "partidas": partidas,
        "tareas": tareas,
    })



# ---------------------------------------------------------------------
# ENDPOINT FINAL ASIGNACIONES
# Nivel queda fuera del flujo operativo.
# Planta = TareaObra.legacy_planta.
# ---------------------------------------------------------------------
def pi_opciones_endpoint_final_sin_nivel(request):
    from django.apps import apps
    from django.http import JsonResponse
    from django.db.models import Q

    ObraPlanificacion = apps.get_model("planificacion_obra", "ObraPlanificacion")
    UnidadObra = apps.get_model("planificacion_obra", "UnidadObra")
    TareaObra = apps.get_model("planificacion_obra", "TareaObra")

    obra_id = request.GET.get("obra") or None
    fase = request.GET.get("fase") or None
    vivienda = request.GET.get("vivienda") or request.GET.get("unidad_obra") or None
    planta = request.GET.get("planta_trabajo") or None
    capitulo_id = request.GET.get("capitulo") or None
    partida_id = request.GET.get("partida") or None

    tareas = TareaObra.objects.select_related(
        "obra",
        "unidad_obra",
        "capitulo",
        "partida",
    ).all()

    if obra_id:
        tareas = tareas.filter(obra_id=obra_id)

    unidades = UnidadObra.objects.all()
    if obra_id:
        unidades = unidades.filter(obra_id=obra_id)

    def field_names(model, keywords, exclude=None):
        exclude = exclude or []
        names = []
        for f in model._meta.fields:
            n = f.name.lower()
            if any(k in n for k in keywords) and not any(e in n for e in exclude):
                names.append(f.name)
        return names

    fase_fields = field_names(UnidadObra, ["fase", "edificio", "bloque"], ["nivel"])
    vivienda_fields = field_names(UnidadObra, ["vivienda", "unidad"], ["nivel", "obra"])

    def obj_value(obj, names):
        for n in names:
            v = getattr(obj, n, None)
            if v not in ("", None):
                return str(v)
        return ""

    def distinct_options_from_units(qs, names):
        values = []
        seen = set()
        for obj in qs:
            v = obj_value(obj, names)
            if v and v not in seen:
                seen.add(v)
                values.append({"id": v, "text": v})
        return values

    fases = distinct_options_from_units(unidades, fase_fields)
    viviendas = distinct_options_from_units(unidades, vivienda_fields)

    if fase and fase_fields:
        q = Q()
        for n in fase_fields:
            q |= Q(**{n: fase})
        unidades = unidades.filter(q)

    if vivienda:
        # Si vivienda viene como pk de unidad_obra, se usa como unidad directa.
        if str(vivienda).isdigit():
            unidades = unidades.filter(pk=vivienda)
        elif vivienda_fields:
            q = Q()
            for n in vivienda_fields:
                q |= Q(**{n: vivienda})
            unidades = unidades.filter(q)

    unidad_ids = list(unidades.values_list("pk", flat=True))

    if fase or vivienda:
        tareas = tareas.filter(unidad_obra_id__in=unidad_ids)

    plantas = list(
        tareas.exclude(legacy_planta__isnull=True)
        .exclude(legacy_planta="")
        .order_by("legacy_planta")
        .values_list("legacy_planta", flat=True)
        .distinct()
    )

    if planta:
        tareas = tareas.filter(legacy_planta=planta)

    capitulos_qs = (
        tareas.exclude(capitulo_id__isnull=True)
        .values_list("capitulo_id", "capitulo__codigo", "capitulo__nombre")
        .distinct()
        .order_by("capitulo__codigo", "capitulo__nombre")
    )

    capitulos = [
        {
            "id": pk,
            "text": " · ".join([x for x in [codigo, nombre] if x]),
        }
        for pk, codigo, nombre in capitulos_qs
    ]

    if capitulo_id:
        tareas = tareas.filter(capitulo_id=capitulo_id)

    partidas_qs = (
        tareas.exclude(partida_id__isnull=True)
        .values_list("partida_id", "partida__codigo", "partida__nombre")
        .distinct()
        .order_by("partida__codigo", "partida__nombre")
    )

    partidas = [
        {
            "id": pk,
            "text": " · ".join([x for x in [codigo, nombre] if x]),
        }
        for pk, codigo, nombre in partidas_qs
    ]

    if partida_id:
        tareas = tareas.filter(partida_id=partida_id)

    tareas_data = [
        {
            "id": t.pk,
            "text": str(t),
        }
        for t in tareas.distinct()[:500]
    ]

    return JsonResponse({
        "fases": fases,
        "viviendas": viviendas,
        "plantas_trabajo": [{"id": p, "text": p} for p in plantas],
        "capitulos": capitulos,
        "partidas": partidas,
        "tareas": tareas_data,
    })


# Aliases defensivos por si urls.py usa otro nombre antiguo.
asignacion_opciones = pi_opciones_endpoint_final_sin_nivel
asignaciones_opciones = pi_opciones_endpoint_final_sin_nivel
opciones_asignacion = pi_opciones_endpoint_final_sin_nivel
asignacion_opciones_view = pi_opciones_endpoint_final_sin_nivel



# ---------------------------------------------------------------------
# ENDPOINT DEFINITIVO COMBOS ASIGNACION
# - Sin nivel.
# - Vivienda devuelve pk real de UnidadObra.
# - Planta = TareaObra.legacy_planta.
# ---------------------------------------------------------------------
def pi_opciones_endpoint_final_sin_nivel(request):
    from django.apps import apps
    from django.http import JsonResponse

    ObraPlanificacion = apps.get_model("planificacion_obra", "ObraPlanificacion")
    UnidadObra = apps.get_model("planificacion_obra", "UnidadObra")
    TareaObra = apps.get_model("planificacion_obra", "TareaObra")

    obra_id = request.GET.get("obra") or None
    fase = request.GET.get("fase") or None
    vivienda_id = request.GET.get("vivienda") or request.GET.get("unidad_obra") or None
    planta = request.GET.get("planta_trabajo") or None
    capitulo_id = request.GET.get("capitulo") or None
    partida_id = request.GET.get("partida") or None

    unidades = UnidadObra.objects.all()

    if obra_id:
        unidades = unidades.filter(obra_id=obra_id)

    def fase_text(unidad):
        for f in unidad._meta.fields:
            name = f.name.lower()

            if "nivel" in name:
                continue

            if "fase" in name or "edificio" in name or "bloque" in name:
                value = getattr(unidad, f.name, None)
                if value not in ("", None):
                    return str(value)

        return ""

    unidades_base = list(unidades.order_by("id"))

    fases = []
    seen_fases = set()

    for unidad in unidades_base:
        text = fase_text(unidad)
        if text and text not in seen_fases:
            seen_fases.add(text)
            fases.append({"id": text, "text": text})

    unidades_filtradas = unidades_base

    if fase:
        unidades_filtradas = [
            u for u in unidades_filtradas
            if fase_text(u) == fase
        ]

    if vivienda_id:
        unidades_filtradas = [
            u for u in unidades_filtradas
            if str(u.pk) == str(vivienda_id)
        ]

    unidad_ids = [u.pk for u in unidades_filtradas]

    viviendas = [
        {
            "id": u.pk,
            "text": str(u),
        }
        for u in unidades_filtradas
    ]

    tareas = TareaObra.objects.select_related(
        "obra",
        "unidad_obra",
        "capitulo",
        "partida",
    ).all()

    if obra_id:
        tareas = tareas.filter(obra_id=obra_id)

    if fase or vivienda_id:
        tareas = tareas.filter(unidad_obra_id__in=unidad_ids)

    plantas = list(
        tareas.exclude(legacy_planta__isnull=True)
        .exclude(legacy_planta="")
        .order_by("legacy_planta")
        .values_list("legacy_planta", flat=True)
        .distinct()
    )

    if planta:
        tareas = tareas.filter(legacy_planta=planta)

    capitulos_qs = (
        tareas.exclude(capitulo_id__isnull=True)
        .values_list("capitulo_id", "capitulo__codigo", "capitulo__nombre")
        .distinct()
        .order_by("capitulo__codigo", "capitulo__nombre")
    )

    capitulos = [
        {
            "id": pk,
            "text": " · ".join([x for x in [codigo, nombre] if x]),
        }
        for pk, codigo, nombre in capitulos_qs
    ]

    if capitulo_id:
        tareas = tareas.filter(capitulo_id=capitulo_id)

    partidas_qs = (
        tareas.exclude(partida_id__isnull=True)
        .values_list("partida_id", "partida__codigo", "partida__nombre")
        .distinct()
        .order_by("partida__codigo", "partida__nombre")
    )

    partidas = [
        {
            "id": pk,
            "text": " · ".join([x for x in [codigo, nombre] if x]),
        }
        for pk, codigo, nombre in partidas_qs
    ]

    if partida_id:
        tareas = tareas.filter(partida_id=partida_id)

    tareas_data = [
        {
            "id": t.pk,
            "text": str(t),
        }
        for t in tareas.distinct()[:500]
    ]

    return JsonResponse({
        "fases": fases,
        "viviendas": viviendas,
        "plantas_trabajo": [{"id": p, "text": p} for p in plantas],
        "capitulos": capitulos,
        "partidas": partidas,
        "tareas": tareas_data,
    })


asignacion_opciones = pi_opciones_endpoint_final_sin_nivel
asignaciones_opciones = pi_opciones_endpoint_final_sin_nivel
opciones_asignacion = pi_opciones_endpoint_final_sin_nivel
asignacion_opciones_view = pi_opciones_endpoint_final_sin_nivel



# Guardia documental:
# El endpoint activo de asignaciones no debe devolver "niveles".
def _pi_strip_niveles_from_response(data):
    try:
        data.pop("niveles", None)
        data.pop("nivel", None)
    except Exception:
        pass
    return data


# ---------------------------------------------------------------------
# ENDPOINT FINAL COMBOS ASIGNACION - ETIQUETAS LIMPIAS
# Obra -> Edificio/Fase -> Vivienda -> Planta
# UnidadObra.nivel NO se muestra ni participa.
# ---------------------------------------------------------------------
def pi_opciones_endpoint_final_sin_nivel(request):
    import re
    from django.apps import apps
    from django.http import JsonResponse

    UnidadObra = apps.get_model("planificacion_obra", "UnidadObra")
    TareaObra = apps.get_model("planificacion_obra", "TareaObra")

    obra_id = request.GET.get("obra") or None
    fase = request.GET.get("fase") or None
    vivienda_id = request.GET.get("vivienda") or request.GET.get("unidad_obra") or None
    planta = request.GET.get("planta_trabajo") or None
    capitulo_id = request.GET.get("capitulo") or None
    partida_id = request.GET.get("partida") or None

    def clean_fase_label(value):
        if value is None:
            return ""

        text = str(value).strip()

        # Extrae "EDIFICIO F" de "2 · ALTOVELOO · EDIFICIO F"
        m = re.search(r"(EDIFICIO\s+[A-Z0-9]+)", text, flags=re.I)
        if m:
            return m.group(1).upper()

        m = re.search(r"(FASE\s+[A-Z0-9]+)", text, flags=re.I)
        if m:
            return m.group(1).upper()

        if "·" in text:
            return text.split("·")[-1].strip()

        return text

    def clean_vivienda_label(unidad):
        # Preferir campo real vivienda si existe.
        for name in ("vivienda", "legacy_cod_vivienda", "cod_vivienda", "codigo_vivienda", "numero_vivienda"):
            if hasattr(unidad, name):
                value = getattr(unidad, name)
                if value not in ("", None):
                    value = str(value).strip()
                    if value.lower().startswith("viv"):
                        return value
                    return f"Viv. {value}"

        # Fallback desde __str__, pero quitando obra/edificio/nivel.
        text = str(unidad)

        m = re.search(r"Viv\.?\s*([A-Za-z0-9\-]+)", text, flags=re.I)
        if m:
            return f"Viv. {m.group(1)}"

        return f"Viv. {unidad.pk}"

    def fase_label_from_unidad(unidad):
        # Buscar campos de fase/edificio sin usar nivel.
        for f in unidad._meta.fields:
            name = f.name.lower()

            if "nivel" in name:
                continue

            if "edificio" in name or "fase" in name or "bloque" in name:
                value = getattr(unidad, f.name, None)
                if value not in ("", None):
                    return clean_fase_label(value)

        # Fallback desde __str__
        return clean_fase_label(str(unidad))

    unidades = UnidadObra.objects.all()

    if obra_id:
        unidades = unidades.filter(obra_id=obra_id)

    unidades_base = list(unidades.order_by("id"))

    fases = []
    seen_fases = set()

    for unidad in unidades_base:
        label = fase_label_from_unidad(unidad)
        if label and label not in seen_fases:
            seen_fases.add(label)
            fases.append({"id": label, "text": label})

    fases = sorted(fases, key=lambda x: x["text"])

    unidades_filtradas = unidades_base

    if fase:
        unidades_filtradas = [
            u for u in unidades_filtradas
            if fase_label_from_unidad(u) == fase
        ]

    if vivienda_id:
        unidades_filtradas = [
            u for u in unidades_filtradas
            if str(u.pk) == str(vivienda_id)
        ]

    unidad_ids = [u.pk for u in unidades_filtradas]

    viviendas = [
        {
            "id": u.pk,
            "text": clean_vivienda_label(u),
        }
        for u in unidades_filtradas
    ]

    viviendas = sorted(viviendas, key=lambda x: x["text"])

    tareas = TareaObra.objects.select_related(
        "obra",
        "unidad_obra",
        "capitulo",
        "partida",
    ).all()

    if obra_id:
        tareas = tareas.filter(obra_id=obra_id)

    if fase or vivienda_id:
        tareas = tareas.filter(unidad_obra_id__in=unidad_ids)

    plantas = list(
        tareas.exclude(legacy_planta__isnull=True)
        .exclude(legacy_planta="")
        .order_by("legacy_planta")
        .values_list("legacy_planta", flat=True)
        .distinct()
    )

    if planta:
        tareas = tareas.filter(legacy_planta=planta)

    capitulos_qs = (
        tareas.exclude(capitulo_id__isnull=True)
        .values_list("capitulo_id", "capitulo__codigo", "capitulo__nombre")
        .distinct()
        .order_by("capitulo__codigo", "capitulo__nombre")
    )

    capitulos = [
        {
            "id": pk,
            "text": " · ".join([x for x in [codigo, nombre] if x]),
        }
        for pk, codigo, nombre in capitulos_qs
    ]

    if capitulo_id:
        tareas = tareas.filter(capitulo_id=capitulo_id)

    partidas_qs = (
        tareas.exclude(partida_id__isnull=True)
        .values_list("partida_id", "partida__codigo", "partida__nombre")
        .distinct()
        .order_by("partida__codigo", "partida__nombre")
    )

    partidas = [
        {
            "id": pk,
            "text": " · ".join([x for x in [codigo, nombre] if x]),
        }
        for pk, codigo, nombre in partidas_qs
    ]

    if partida_id:
        tareas = tareas.filter(partida_id=partida_id)

    tareas_data = [
        {
            "id": t.pk,
            "text": str(t),
        }
        for t in tareas.distinct()[:500]
    ]

    return JsonResponse({
        "fases": fases,
        "viviendas": viviendas,
        "plantas_trabajo": [{"id": p, "text": p} for p in plantas],
        "capitulos": capitulos,
        "partidas": partidas,
        "tareas": tareas_data,
    })


asignacion_opciones = pi_opciones_endpoint_final_sin_nivel
asignaciones_opciones = pi_opciones_endpoint_final_sin_nivel
opciones_asignacion = pi_opciones_endpoint_final_sin_nivel
asignacion_opciones_view = pi_opciones_endpoint_final_sin_nivel


# ---------------------------------------------------------------------
# Acciones planificación de personal: abrir / editar / eliminar
# ---------------------------------------------------------------------

@login_required
def realizado_detail(request, pk):
    from decimal import Decimal
    from django.apps import apps
    from django.shortcuts import get_object_or_404, render

    TareaRecursoReal = apps.get_model("planificacion_obra", "TareaRecursoReal")

    qs = TareaRecursoReal.objects.select_related(
        "team",
        "empleado",
        "empleado__rrhh_empleado",
        "tarea_obra",
        "tarea_obra__obra",
        "unidad_obra",
        "partida",
    ).filter(
        empleado__isnull=False,
        tarea_obra__isnull=False,
        inicio_recurso_real__isnull=False,
        legacy_tipo_recurso__in=["M.O. ADM.", "PER. CONT.", "M.O. CONT."],
    )

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs = qs.filter(team__in=request.user.teams.all())

    realizado = get_object_or_404(qs, pk=pk)

    horas = realizado.cantidad or Decimal("0")
    precio_hora = realizado.precio_unidad or Decimal("0")
    importe = horas * precio_hora

    def money(value):
        return f"{Decimal(value or 0).quantize(Decimal('0.01'))}"

    def hours(value):
        return f"{Decimal(value or 0).quantize(Decimal('0.01'))}"

    tarea = realizado.tarea_obra
    obra = getattr(tarea, "obra", None)
    unidad = realizado.unidad_obra or getattr(tarea, "unidad_obra", None)

    def clean(value, default="-"):
        return value if value not in ("", None) else default

    vivienda = clean(getattr(unidad, "vivienda", None), clean(realizado.legacy_cod_vivienda))
    if vivienda != "-" and str(vivienda) != "0":
        vivienda = f"Viv. {vivienda}"
    elif str(vivienda) == "0":
        vivienda = "Obra"

    # Capítulo/partida visual desde FK real.
    # En Access algunos históricos traen legacy_capitulo vacío, pero la FK partida
    # sí conoce su capítulo correcto.
    realizado_partida_obj = (
        getattr(realizado, "partida", None)
        or getattr(getattr(realizado, "tarea_obra", None), "partida", None)
    )
    realizado_capitulo_obj = (
        getattr(realizado_partida_obj, "capitulo", None)
        or getattr(getattr(realizado, "tarea_obra", None), "capitulo", None)
    )

    def _realizado_catalog_label(obj, fallback=""):
        codigo = str(getattr(obj, "codigo", "") or "").strip()
        nombre = str(getattr(obj, "nombre", "") or "").strip()
        fallback = clean(fallback)
        if codigo and nombre:
            return f"{codigo} · {nombre}"
        return nombre or codigo or fallback or "-"

    capitulo_display = _realizado_catalog_label(
        realizado_capitulo_obj,
        getattr(realizado, "legacy_capitulo", ""),
    )
    partida_display = _realizado_catalog_label(
        realizado_partida_obj,
        getattr(realizado, "legacy_partida", ""),
    )

    context = {
        "realizado": realizado,
        "horas": horas,
        "precio_hora": precio_hora,
        "importe": importe,
        "horas_display": hours(horas),
        "precio_hora_display": money(precio_hora),
        "importe_display": money(importe),
        "importe_registrado_display": money(realizado.costo_recurso_real),
        "obra": clean(obra),
        "edificio": clean(getattr(unidad, "edificio", None), ""),
        "vivienda": vivienda,
        "planta": clean(realizado.legacy_planta),
        "capitulo": capitulo_display,
        "partida": partida_display,
        "empleado": clean(realizado.empleado),
        "fecha": realizado.inicio_recurso_real,
        "observaciones": clean(realizado.observaciones, ""),
        "es_generado_portal": bool(realizado.legacy_id_recurso_tarea and realizado.legacy_id_recurso_tarea >= 300000),
    }

    return render(request, "planificacion_obra/realizado_detail.html", context)

@login_required
def asignacion_detail(request, pk):
    from django.shortcuts import get_object_or_404, render
    from django.utils import timezone
    from .models import AsignacionObra

    qs = AsignacionObra.objects.select_related(
        "team", "empleado", "tarea_obra", "unidad_obra", "capitulo", "partida"
    )

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs = qs.filter(team__in=request.user.teams.all())

    asignacion = get_object_or_404(qs, pk=pk)

    today = timezone.localdate()
    puede_marcar_realizado = (
        asignacion.estado != AsignacionObra.Estado.REALIZADO
        and asignacion.fecha_inicio <= today
        and asignacion.fecha_fin <= today
    )

    back_url = request.GET.get("next") or request.META.get("HTTP_REFERER") or "/app/planificacion-obra/asignaciones/"
    return render(request, "planificacion_obra/asignacion_detail.html", {
        "back_url": back_url,
        "asignacion": asignacion,
        "today": today,
        "puede_marcar_realizado": puede_marcar_realizado,
    })


@login_required
def asignacion_realizar(request, pk):
    from django.contrib import messages
    from django.shortcuts import get_object_or_404, redirect
    from django.urls import reverse
    from django.utils import timezone
    from .models import AsignacionObra
    from .services_realizacion import realizar_asignacion_obra, RealizacionAsignacionError

    qs = AsignacionObra.objects.select_related(
        "team", "empleado", "tarea_obra", "unidad_obra", "capitulo", "partida"
    )

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs = qs.filter(team__in=request.user.teams.all())

    asignacion = get_object_or_404(qs, pk=pk)

    if request.method != "POST":
        return redirect("planificacion_obra:asignacion_detail", pk=asignacion.pk)

    today = timezone.localdate()
    if asignacion.fecha_inicio > today or asignacion.fecha_fin > today:
        messages.warning(
            request,
            "La asignación está en fecha futura. Ajusta la fecha real de ejecución antes de marcarla como realizada."
        )
        edit_url = reverse("planificacion_obra:asignacion_update", kwargs={"pk": asignacion.pk})
        return redirect(f"{edit_url}?ajustar_realizado=1")

    anterior = snapshot_asignacion(
        asignacion
    )

    recurso_real_anteriores_ids = (
        _asignacion_recurso_real_portal_ids(
            asignacion
        )
    )

    operation_id = _tm_uuid4().hex

    try:
        with transaction.atomic():
            recurso_real = (
                realizar_asignacion_obra(
                    asignacion,
                    user=request.user,
                )
            )

            asignacion.refresh_from_db()

            recurso_real_ids = (
                _asignacion_recurso_real_portal_ids(
                    asignacion
                )
            )

            if (
                getattr(
                    recurso_real,
                    "pk",
                    None,
                )
                and recurso_real.pk
                not in recurso_real_ids
            ):
                recurso_real_ids.append(
                    recurso_real.pk
                )

                recurso_real_ids.sort()

            recurso_real_creados = len(
                set(recurso_real_ids)
                - set(
                    recurso_real_anteriores_ids
                )
            )

            recurso_real_actualizados = (
                1
                if (
                    recurso_real_ids
                    and not recurso_real_creados
                )
                else 0
            )

            registrar_realizacion_asignacion(
                asignacion=asignacion,
                actor=request.user,
                anterior=anterior,
                recurso_real_ids=(
                    recurso_real_ids
                ),
                recurso_real_creados=(
                    recurso_real_creados
                ),
                recurso_real_actualizados=(
                    recurso_real_actualizados
                ),
                fuente="accion_realizar",
                operation_id=operation_id,
            )

    except RealizacionAsignacionError as exc:
        messages.error(
            request,
            str(exc),
        )

    except Exception as exc:
        messages.error(
            request,
            (
                "No se pudo marcar como "
                f"realizado: {exc}"
            ),
        )

    else:
        messages.success(
            request,
            (
                f"Asignación #{asignacion.id} "
                "marcada como realizada. "
                f"Recurso real "
                f"#{recurso_real.id} "
                "creado/actualizado."
            ),
        )

    next_url = request.POST.get("next")
    if next_url:
        return redirect(next_url)

    return redirect("planificacion_obra:asignacion_detail", pk=asignacion.pk)


@login_required
def asignacion_update(request, pk):
    from datetime import datetime
    from django.shortcuts import get_object_or_404, redirect, render
    from django.contrib import messages
    from django.utils import timezone
    from django.utils.dateparse import parse_date, parse_time
    from .models import AsignacionObra
    from .forms import AsignacionObraForm

    qs = AsignacionObra.objects.select_related(
        "team", "empleado", "tarea_obra", "unidad_obra", "capitulo", "partida"
    )

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs = qs.filter(team__in=request.user.teams.all())

    asignacion = get_object_or_404(qs, pk=pk)

    anterior = (
        snapshot_asignacion(
            asignacion
        )
        if request.method == "POST"
        else None
    )

    recurso_real_anteriores_ids = (
        _asignacion_recurso_real_portal_ids(
            asignacion
        )
        if request.method == "POST"
        else []
    )

    modo_ajuste_realizado = (
        request.GET.get("ajustar_realizado") == "1"
        or request.POST.get("modo") == "ajustar_realizado"
    )

    today = timezone.localdate()

    def build_context(form, values=None):
        values = values or {}
        return {
            "form": form,
            "empleado_precios_json": _planificacion_empleado_precios_json(),
            "asignacion": asignacion,
            "modo_ajuste_realizado": modo_ajuste_realizado,
            "ajuste_fecha_inicio_value": values.get("fecha_inicio") or today.isoformat(),
            "ajuste_fecha_fin_value": values.get("fecha_fin") or today.isoformat(),
            "ajuste_hora_inicio_value": values.get("hora_inicio") or asignacion.hora_inicio.strftime("%H:%M"),
            "ajuste_hora_fin_value": values.get("hora_fin") or asignacion.hora_fin.strftime("%H:%M"),
        }

    if request.method == "POST" and modo_ajuste_realizado:
        fecha_inicio_raw = request.POST.get("fecha_inicio") or ""
        fecha_fin_raw = request.POST.get("fecha_fin") or ""
        hora_inicio_raw = request.POST.get("hora_inicio") or ""
        hora_fin_raw = request.POST.get("hora_fin") or ""

        fecha_inicio = parse_date(fecha_inicio_raw)
        fecha_fin = parse_date(fecha_fin_raw)
        hora_inicio = parse_time(hora_inicio_raw)
        hora_fin = parse_time(hora_fin_raw)

        errores = []

        if not fecha_inicio:
            errores.append("Fecha inicio no válida.")
        if not fecha_fin:
            errores.append("Fecha fin no válida.")
        if not hora_inicio:
            errores.append("Hora inicio no válida.")
        if not hora_fin:
            errores.append("Hora fin no válida.")

        if fecha_inicio and fecha_inicio > today:
            errores.append("La fecha inicio real no puede ser futura.")
        if fecha_fin and fecha_fin > today:
            errores.append("La fecha fin real no puede ser futura.")

        if fecha_inicio and fecha_fin and hora_inicio and hora_fin:
            inicio_dt = datetime.combine(fecha_inicio, hora_inicio)
            fin_dt = datetime.combine(fecha_fin, hora_fin)
            if fin_dt <= inicio_dt:
                errores.append("La fecha/hora fin debe ser posterior a la fecha/hora inicio.")

        if errores:
            for error in errores:
                messages.error(request, error)

            form = AsignacionObraForm(instance=asignacion, request_user=request.user)
            return render(
                request,
                "planificacion_obra/asignacion_form.html",
                build_context(form, {
                    "fecha_inicio": fecha_inicio_raw,
                    "fecha_fin": fecha_fin_raw,
                    "hora_inicio": hora_inicio_raw,
                    "hora_fin": hora_fin_raw,
                }),
            )

        operation_id = _tm_uuid4().hex

        with transaction.atomic():
            asignacion.fecha_inicio = (
                fecha_inicio
            )
            asignacion.fecha_fin = (
                fecha_fin
            )
            asignacion.hora_inicio = (
                hora_inicio
            )
            asignacion.hora_fin = (
                hora_fin
            )

            asignacion.save(
                update_fields=[
                    "fecha_inicio",
                    "fecha_fin",
                    "hora_inicio",
                    "hora_fin",
                    "actualizado_en",
                ]
            )

            recurso_real_ids = (
                _asignacion_recurso_real_portal_ids(
                    asignacion
                )
            )

            registrar_cambio_asignacion(
                asignacion=asignacion,
                actor=request.user,
                anterior=anterior,
                fuente=(
                    "ajuste_previo_realizar"
                ),
                operation_id=operation_id,
                recurso_real_ids=(
                    recurso_real_ids
                ),
                recurso_real_anteriores_ids=(
                    recurso_real_anteriores_ids
                ),
            )

        messages.success(
            request,
            (
                "Fecha y horario real "
                "ajustados. Ahora puedes "
                "marcar la asignación "
                "como realizada."
            ),
        )

        return redirect(
            (
                "planificacion_obra:"
                "asignacion_detail"
            ),
            pk=asignacion.pk,
        )

    if request.method == "POST":
        form = AsignacionObraForm(request.POST, instance=asignacion, request_user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)

            if getattr(obj, "team_id", None) is None and getattr(obj, "tarea_obra", None):
                obj.team = obj.tarea_obra.team

            operation_id = (
                _tm_uuid4().hex
            )

            with transaction.atomic():
                # ASIGNACION_APLICAR_AVANCE_ASIGNACION_UPDATE_V1_1
                _asignacion_aplicar_avance_tarea(
                    form=form,
                    asignacion=obj,
                )

                estado_sync, estado_msg = (
                    _asignacion_guardar_y_sincronizar_estado(
                        obj,
                        user=request.user,
                    )
                )

                recurso_real_ids = (
                    _asignacion_recurso_real_portal_ids(
                        obj
                    )
                )

                registrar_cambio_asignacion(
                    asignacion=obj,
                    actor=request.user,
                    anterior=anterior,
                    fuente="formulario",
                    operation_id=operation_id,
                    recurso_real_ids=(
                        recurso_real_ids
                    ),
                    recurso_real_anteriores_ids=(
                        recurso_real_anteriores_ids
                    ),
                )

            if estado_sync == "realizado":
                messages.success(request, estado_msg)
            elif estado_sync == "pendiente_forzada":
                messages.warning(request, estado_msg)
            elif estado_sync == "pendiente":
                messages.success(request, estado_msg)
            else:
                messages.error(request, estado_msg or "No se pudo sincronizar la asignación.")

            return redirect("planificacion_obra:asignaciones_list")
    else:
        initial = {}
        if asignacion.tarea_obra_id:
            initial["obra"] = asignacion.tarea_obra.obra_id
            initial["planta_trabajo"] = asignacion.tarea_obra.legacy_planta
            if asignacion.unidad_obra_id:
                initial["vivienda"] = asignacion.unidad_obra_id

        if modo_ajuste_realizado:
            initial["fecha_inicio"] = today
            initial["fecha_fin"] = today
            initial["hora_inicio"] = asignacion.hora_inicio
            initial["hora_fin"] = asignacion.hora_fin

        form = AsignacionObraForm(instance=asignacion, initial=initial, request_user=request.user)

    return render(
        request,
        "planificacion_obra/asignacion_form.html",
        build_context(form),
    )


@login_required
def asignacion_delete(request, pk):
    from django.shortcuts import get_object_or_404, redirect, render
    from django.contrib import messages
    from .models import AsignacionObra

    qs = AsignacionObra.objects.select_related(
        "team", "empleado", "tarea_obra", "unidad_obra", "capitulo", "partida"
    )

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs = qs.filter(team__in=request.user.teams.all())

    asignacion = get_object_or_404(qs, pk=pk)

    if request.method == "POST":
        anterior = snapshot_asignacion(
            asignacion
        )

        recurso_real_relacionados_ids = (
            _asignacion_recurso_real_portal_ids(
                asignacion
            )
        )

        operation_id = _tm_uuid4().hex

        with transaction.atomic():
            registrar_eliminacion_asignacion(
                asignacion=asignacion,
                actor=request.user,
                anterior=anterior,
                fuente="formulario",
                operation_id=operation_id,
                recurso_real_relacionados_ids=(
                    recurso_real_relacionados_ids
                ),
            )

            asignacion.delete()

        messages.success(
            request,
            (
                "Asignación eliminada "
                "correctamente."
            ),
        )

        return redirect(
            (
                "planificacion_obra:"
                "asignaciones_list"
            )
        )

    return render(request, "planificacion_obra/asignacion_confirm_delete.html", {
        "asignacion": asignacion,
    })


# ---------------------------------------------------------------------
# Calendario visual de asignaciones de personal
# ---------------------------------------------------------------------
@login_required
def asignaciones_calendario(request):
    from django.apps import apps
    from django.shortcuts import render

    AsignacionObra = apps.get_model("planificacion_obra", "AsignacionObra")
    TareaRecursoReal = apps.get_model("planificacion_obra", "TareaRecursoReal")
    ObraPlanificacion = apps.get_model("planificacion_obra", "ObraPlanificacion")
    UnidadObra = apps.get_model("planificacion_obra", "UnidadObra")
    TareaObra = apps.get_model("planificacion_obra", "TareaObra")
    CapituloCatalogo = apps.get_model("planificacion_obra", "CapituloCatalogo")
    PartidaCatalogo = apps.get_model("planificacion_obra", "PartidaCatalogo")
    TareaRecursoReal = apps.get_model("planificacion_obra", "TareaRecursoReal")
    from .forms import AsignacionObraForm

    qs = AsignacionObra.objects.all()

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs = qs.filter(team__in=request.user.teams.all())
    obras = ObraPlanificacion.objects.all().order_by("codigo", "id")

    # Usar exactamente el mismo queryset de empleados que el formulario de nueva asignación.
    form_ref = AsignacionObraForm()
    empleados = form_ref.fields["empleado"].queryset

    edificios = (
        UnidadObra.objects
        .exclude(edificio__isnull=True)
        .exclude(edificio="")
        .values_list("edificio", flat=True)
        .distinct()
        .order_by("edificio")
    )

    viviendas = (
        UnidadObra.objects
        .exclude(vivienda__isnull=True)
        .exclude(vivienda="")
        .values_list("vivienda", flat=True)
        .distinct()
        .order_by("vivienda")
    )

    plantas = (
        TareaObra.objects
        .exclude(legacy_planta__isnull=True)
        .exclude(legacy_planta="")
        .values_list("legacy_planta", flat=True)
        .distinct()
        .order_by("legacy_planta")
    )

    capitulos = CapituloCatalogo.objects.all().order_by("codigo", "orden", "id")
    partidas = PartidaCatalogo.objects.select_related("capitulo").all().order_by("codigo", "id")

    estados = AsignacionObra._meta.get_field("estado").choices

    return render(request, "planificacion_obra/asignaciones_calendario.html", {
        "obras": obras,
        "empleados": empleados,
        "edificios": edificios,
        "viviendas": viviendas,
        "plantas": plantas,
        "capitulos": capitulos,
        "partidas": partidas,
        "estados": estados,
    })


@login_required
def asignaciones_calendario_feed(request):
    from datetime import datetime, time, timedelta
    from django.apps import apps
    from django.db.models import Q
    from django.http import JsonResponse
    from django.utils import timezone

    AsignacionObra = apps.get_model("planificacion_obra", "AsignacionObra")
    TareaRecursoReal = apps.get_model("planificacion_obra", "TareaRecursoReal")

    today = timezone.localdate()

    obra_id = request.GET.get("obra") or ""
    empleado_id = request.GET.get("empleado") or ""
    edificio = request.GET.get("edificio") or ""
    vivienda = request.GET.get("vivienda") or ""
    planta = request.GET.get("planta") or ""
    capitulo_id = request.GET.get("capitulo") or ""
    partida_id = request.GET.get("partida") or ""
    estado = request.GET.get("estado") or ""

    start_param = request.GET.get("start")
    end_param = request.GET.get("end")

    start_date = None
    end_date = None

    if start_param:
        try:
            start_date = datetime.fromisoformat(start_param.replace("Z", "+00:00")).date()
        except Exception:
            start_date = None

    if end_param:
        try:
            end_date = datetime.fromisoformat(end_param.replace("Z", "+00:00")).date()
        except Exception:
            end_date = None

    def by_team(qs):
        if not request.user.is_superuser and hasattr(request.user, "teams"):
            return qs.filter(team__in=request.user.teams.all())
        return qs

    def aware_dt(fecha, hora):
        if not fecha:
            return None
        hora = hora or time(8, 0)
        dt = datetime.combine(fecha, hora)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt

    def safe_attr(obj, attr, default="-"):
        try:
            value = getattr(obj, attr)
            return value if value not in ("", None) else default
        except Exception:
            return default

    def vivienda_label(cod):
        cod = str(cod or "").strip()
        if not cod or cod == "0":
            return "Obra"
        return f"Viv. {cod}"

    colors = {
        "PENDIENTE": {"background": "#2563eb", "text": "#ffffff"},
        "REALIZADO": {"background": "#16a34a", "text": "#ffffff"},
        "HISTORICO": {"background": "#15803d", "text": "#ffffff"},
    }

    events = []

    # ------------------------------------------------------
    # Portal: asignaciones planificadas o realizadas
    # ------------------------------------------------------
    qs = AsignacionObra.objects.select_related(
        "team",
        "empleado",
        "tarea_obra",
        "unidad_obra",
        "capitulo",
        "partida",
    )
    qs = by_team(qs)

    if obra_id.isdigit():
        qs = qs.filter(tarea_obra__obra_id=int(obra_id))
    if empleado_id.isdigit():
        qs = qs.filter(empleado_id=int(empleado_id))
    if edificio:
        qs = qs.filter(unidad_obra__edificio=edificio)
    if vivienda:
        qs = qs.filter(unidad_obra__vivienda=vivienda)
    if planta:
        qs = qs.filter(tarea_obra__legacy_planta=planta)
    if capitulo_id.isdigit():
        qs = qs.filter(capitulo_id=int(capitulo_id))
    if partida_id.isdigit():
        qs = qs.filter(partida_id=int(partida_id))
    if estado:
        qs = qs.filter(estado=estado)

    if start_date:
        qs = qs.filter(fecha_inicio__gte=start_date)
    if end_date:
        qs = qs.filter(fecha_inicio__lt=end_date)

    # PI_PERSONAL_UNIFIED_REAL_300K_DEDUPE_V3
    portal_real_legacy_ids = {
        300000 + int(pk)
        for pk in qs.values_list("id", flat=True)
    }

    for a in qs.order_by("fecha_inicio", "hora_inicio", "empleado_id")[:1000]:
        start = aware_dt(a.fecha_inicio, a.hora_inicio)
        end = aware_dt(a.fecha_fin or a.fecha_inicio, a.hora_fin)

        if not start:
            continue

        empleado = str(a.empleado) if a.empleado_id else "Sin empleado"
        vivienda_txt = safe_attr(a, "pi_display_vivienda_corta")
        planta_txt = safe_attr(a, "pi_display_planta")
        obra_txt = safe_attr(a, "pi_display_obra")
        capitulo_txt = safe_attr(a, "pi_display_capitulo")
        partida_txt = safe_attr(a, "pi_display_partida")

        estado_key = str(a.estado or "").upper()
        color = colors.get(estado_key, colors["PENDIENTE"])

        origen = "Portal · Realizado" if estado_key == "REALIZADO" else "Portal · Planificado"
        title = f"{empleado} · {vivienda_txt} · {planta_txt}"

        events.append({
            "id": f"asig-{a.pk}",
            "title": title,
            "start": start.isoformat(),
            "end": end.isoformat() if end else None,
            "url": f"/app/planificacion-obra/asignaciones/{a.pk}/?next=/app/planificacion-obra/asignaciones/calendario/",
            "backgroundColor": color["background"],
            "borderColor": color["background"],
            "textColor": color["text"],
            "extendedProps": {
                "source": "portal",
                "empleado": empleado,
                "obra": obra_txt,
                "vivienda": vivienda_txt,
                "planta": planta_txt,
                "capitulo": capitulo_txt,
                "partida": partida_txt,
                "estado": a.get_estado_display(),
                "origen": origen,
            },
        })

    # ------------------------------------------------------
    # Histórico real legacy
    # ------------------------------------------------------
    qs_real = TareaRecursoReal.objects.select_related(
        "team",
        "empleado",
        "empleado__rrhh_empleado",
        "tarea_obra",
        "tarea_obra__obra",
        "unidad_obra",
        "partida",
    ).filter(
        empleado__isnull=False,
        tarea_obra__isnull=False,
        inicio_recurso_real__isnull=False,
        inicio_recurso_real__lt=today,
        legacy_tipo_recurso__in=["M.O. ADM.", "PER. CONT.", "M.O. CONT."],
    )

    qs_real = by_team(qs_real)

    # PI_PERSONAL_UNIFIED_REAL_300K_DEDUPE_V3
    if portal_real_legacy_ids:
        qs_real = qs_real.exclude(legacy_id_recurso_tarea__in=portal_real_legacy_ids)


    if obra_id.isdigit():
        qs_real = qs_real.filter(tarea_obra__obra_id=int(obra_id))
    if empleado_id.isdigit():
        qs_real = qs_real.filter(empleado__rrhh_empleado_id=int(empleado_id))
    if edificio:
        qs_real = qs_real.filter(unidad_obra__edificio=edificio)
    if vivienda:
        qs_real = qs_real.filter(unidad_obra__vivienda=vivienda)
    if planta:
        qs_real = qs_real.filter(legacy_planta=planta)
    if capitulo_id.isdigit():
        qs_real = qs_real.filter(tarea_obra__capitulo_id=int(capitulo_id))
    if partida_id.isdigit():
        qs_real = qs_real.filter(Q(partida_id=int(partida_id)) | Q(tarea_obra__partida_id=int(partida_id)))

    if estado and estado != "REALIZADO":
        qs_real = qs_real.none()

    if start_date:
        qs_real = qs_real.filter(inicio_recurso_real__gte=start_date)
    if end_date:
        qs_real = qs_real.filter(inicio_recurso_real__lt=end_date)

    for r in qs_real.order_by("inicio_recurso_real", "empleado_id", "id")[:1500]:
        empleado = str(r.empleado) if r.empleado_id else "Sin empleado"
        vivienda_txt = vivienda_label(r.legacy_cod_vivienda)
        planta_txt = r.legacy_planta or "-"
        obra_obj = getattr(r.tarea_obra, "obra", None)
        obra_txt = str(obra_obj) if obra_obj else str(r.legacy_cod_obra or "-")
        capitulo_txt = r.legacy_capitulo or "-"
        partida_txt = (
            getattr(getattr(r, "partida", None), "nombre", "")
            or getattr(getattr(getattr(r, "tarea_obra", None), "partida", None), "nombre", "")
            or getattr(r, "legacy_partida", "")
            or "-"
        )
        horas_txt = f" · {r.cantidad} h" if r.cantidad else ""

        fecha = r.inicio_recurso_real
        end_fecha = fecha + timedelta(days=1)

        title = f"{empleado} · {vivienda_txt} · {planta_txt}{horas_txt}"
        color = colors["HISTORICO"]

        events.append({
            "id": f"real-{r.pk}",
            "title": title,
            "start": fecha.isoformat(),
            "url": f"/app/planificacion-obra/realizados/{r.pk}/?next=/app/planificacion-obra/asignaciones/calendario/",
            "end": end_fecha.isoformat(),
            "allDay": True,
            "backgroundColor": color["background"],
            "borderColor": color["background"],
            "textColor": color["text"],
            "extendedProps": {
                "source": "historico",
                "empleado": empleado,
                "obra": obra_txt,
                "vivienda": vivienda_txt,
                "planta": planta_txt,
                "capitulo": capitulo_txt,
                "partida": partida_txt,
                "estado": "Realizado",
                "origen": "Realizado",
            },
        })

    return JsonResponse(events, safe=False)

# ---------------------------------------------------------------------
# Opciones dependientes para filtros del calendario de asignaciones
# ---------------------------------------------------------------------
@login_required
def asignaciones_calendario_filtros(request):
    from django.apps import apps
    from django.http import JsonResponse

    UnidadObra = apps.get_model("planificacion_obra", "UnidadObra")
    TareaObra = apps.get_model("planificacion_obra", "TareaObra")
    CapituloCatalogo = apps.get_model("planificacion_obra", "CapituloCatalogo")
    PartidaCatalogo = apps.get_model("planificacion_obra", "PartidaCatalogo")

    obra_id = request.GET.get("obra") or ""
    edificio = request.GET.get("edificio") or ""
    vivienda = request.GET.get("vivienda") or ""
    planta = request.GET.get("planta") or ""
    capitulo_id = request.GET.get("capitulo") or ""

    unidades = UnidadObra.objects.all()
    tareas = TareaObra.objects.select_related("unidad_obra", "capitulo", "partida")

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        user_teams = request.user.teams.all()
        unidades = unidades.filter(team__in=user_teams)
        tareas = tareas.filter(team__in=user_teams)

    if obra_id.isdigit():
        unidades = unidades.filter(obra_id=int(obra_id))
        tareas = tareas.filter(obra_id=int(obra_id))

    # Edificios disponibles dentro de la obra seleccionada
    edificios_qs = (
        unidades
        .exclude(edificio__isnull=True)
        .exclude(edificio="")
        .values_list("edificio", flat=True)
        .distinct()
    )
    edificios = sorted(set(edificios_qs))

    if edificio:
        unidades = unidades.filter(edificio=edificio)
        tareas = tareas.filter(unidad_obra__edificio=edificio)

    # Viviendas disponibles dentro de obra + edificio
    viviendas_qs = (
        unidades
        .exclude(vivienda__isnull=True)
        .exclude(vivienda="")
        .values_list("vivienda", flat=True)
        .distinct()
    )

    def vivienda_sort_key(v):
        s = str(v)
        return (0, int(s)) if s.isdigit() else (1, s)

    viviendas = sorted(set(viviendas_qs), key=vivienda_sort_key)

    if vivienda:
        unidades = unidades.filter(vivienda=vivienda)
        tareas = tareas.filter(unidad_obra__vivienda=vivienda)

    # Plantas disponibles dentro de obra + edificio + vivienda
    plantas_qs = (
        tareas
        .exclude(legacy_planta__isnull=True)
        .exclude(legacy_planta="")
        .values_list("legacy_planta", flat=True)
        .distinct()
    )
    plantas = sorted(set(plantas_qs))

    if planta:
        tareas = tareas.filter(legacy_planta=planta)

    # Capítulos disponibles según ubicación/planta actual
    capitulo_ids = tareas.exclude(capitulo_id__isnull=True).values_list("capitulo_id", flat=True).distinct()
    capitulos = CapituloCatalogo.objects.filter(id__in=capitulo_ids).order_by("codigo", "orden", "id")

    if capitulo_id.isdigit():
        tareas = tareas.filter(capitulo_id=int(capitulo_id))

    # Partidas disponibles según ubicación/planta/capítulo actual
    partida_ids = tareas.exclude(partida_id__isnull=True).values_list("partida_id", flat=True).distinct()
    partidas = PartidaCatalogo.objects.filter(id__in=partida_ids).select_related("capitulo").order_by("codigo", "id")

    return JsonResponse({
        "edificios": [{"id": x, "text": x} for x in edificios],
        "viviendas": [{"id": x, "text": f"Viv. {x}"} for x in viviendas],
        "plantas": [{"id": x, "text": x} for x in plantas],
        "capitulos": [{"id": c.pk, "text": str(c)} for c in capitulos],
        "partidas": [{"id": p.pk, "text": str(p)} for p in partidas],
    })

# ---------------------------------------------------------------------
# Gantt visual de planificación de asignaciones
# ---------------------------------------------------------------------
@login_required

def asignaciones_gantt(request):
    from urllib.parse import quote
    gantt_next_url = quote(request.get_full_path())
    from datetime import date, timedelta
    from django.apps import apps
    from django.db.models import Q
    from django.shortcuts import render
    from django.utils import timezone

    AsignacionObra = apps.get_model("planificacion_obra", "AsignacionObra")
    ObraPlanificacion = apps.get_model("planificacion_obra", "ObraPlanificacion")
    UnidadObra = apps.get_model("planificacion_obra", "UnidadObra")
    TareaObra = apps.get_model("planificacion_obra", "TareaObra")
    CapituloCatalogo = apps.get_model("planificacion_obra", "CapituloCatalogo")
    PartidaCatalogo = apps.get_model("planificacion_obra", "PartidaCatalogo")

    from .forms import AsignacionObraForm

    today = timezone.localdate()

    def parse_date(value, default):
        try:
            return date.fromisoformat(value)
        except Exception:
            return default

    fecha_desde = parse_date(request.GET.get("desde"), today)
    fecha_hasta = parse_date(request.GET.get("hasta"), today + timedelta(days=21))

    if fecha_hasta < fecha_desde:
        fecha_hasta = fecha_desde

    # Limitar rango para no crear una tabla inmanejable.
    if (fecha_hasta - fecha_desde).days > 90:
        fecha_hasta = fecha_desde + timedelta(days=90)

    obra_id = request.GET.get("obra") or ""
    edificio = request.GET.get("edificio") or ""
    vivienda = request.GET.get("vivienda") or ""
    planta = request.GET.get("planta") or ""
    capitulo_id = request.GET.get("capitulo") or ""
    partida_id = request.GET.get("partida") or ""
    empleado_id = request.GET.get("empleado") or ""
    estado = request.GET.get("estado") or ""
    agrupacion = request.GET.get("agrupacion") or "asignacion"
    vista_gantt = request.GET.get("vista") == "gantt"

    if agrupacion not in ("asignacion", "vivienda", "empleado", "capitulo", "partida"):
        agrupacion = "asignacion"

    qs = AsignacionObra.objects.select_related(
        "team",
        "empleado",
        "tarea_obra",
        "unidad_obra",
        "capitulo",
        "partida",
    )

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs = qs.filter(team__in=request.user.teams.all())

    # Asignaciones que se solapan con el periodo.
    qs = qs.filter(fecha_inicio__lte=fecha_hasta).filter(
        Q(fecha_fin__gte=fecha_desde) |
        Q(fecha_fin__isnull=True, fecha_inicio__gte=fecha_desde)
    )

    if obra_id.isdigit():
        qs = qs.filter(tarea_obra__obra_id=int(obra_id))

    if edificio:
        qs = qs.filter(unidad_obra__edificio=edificio)

    if vivienda:
        qs = qs.filter(unidad_obra__vivienda=vivienda)

    if planta:
        qs = qs.filter(tarea_obra__legacy_planta=planta)

    if capitulo_id.isdigit():
        qs = qs.filter(capitulo_id=int(capitulo_id))

    if partida_id.isdigit():
        qs = qs.filter(partida_id=int(partida_id))

    if empleado_id.isdigit():
        qs = qs.filter(empleado_id=int(empleado_id))

    if estado:
        qs = qs.filter(estado=estado)

    # PI_PERSONAL_UNIFIED_REAL_300K_DEDUPE_V3
    portal_real_legacy_ids = {
        300000 + int(pk)
        for pk in qs.values_list("id", flat=True)
    }


    days = []
    cursor = fecha_desde
    while cursor <= fecha_hasta:
        days.append(cursor)
        cursor += timedelta(days=1)

    def display_attr(obj, attr, default="-"):
        try:
            value = getattr(obj, attr)
            return value if value not in ("", None) else default
        except Exception:
            return default

    estado_classes = {
        "PENDIENTE": "pendiente",
        "REALIZADO": "completada",
        "EN_PROCESO": "proceso",
        "COMPLETADA": "completada",
        "FINALIZADA": "completada",
        "BLOQUEADA": "bloqueada",
        "CANCELADA": "cancelada",
    }

    rows = []

    def fmt_hora(h):
        return h.strftime("%H:%M") if h else ""

    def fmt_hora_compacta(h):
        if not h:
            return ""
        if getattr(h, "minute", 0) == 0:
            return h.strftime("%H")
        return h.strftime("%H:%M")

    def vivienda_label(cod):
        cod = str(cod or "").strip()
        if not cod or cod == "0":
            return "Obra"
        return f"Viv. {cod}"

    def fmt_horas_gantt(value):
        if value in ("", None):
            return ""
        try:
            num = float(value)
        except (TypeError, ValueError):
            return str(value)

        if num.is_integer():
            return str(int(num))

        return f"{num:.1f}".rstrip("0").rstrip(".")

    def build_cells(start, end, compact_label, full_label):
        cells = []
        for d in days:
            active = start <= d <= end
            first_visible = max(start, fecha_desde)
            cells.append({
                "date": d,
                "active": active,
                "is_start": active and d == first_visible,
                "label": compact_label if active and d == first_visible else "",
                "full_label": full_label if active else "",
            })
        return cells

    # ------------------------------------------------------
    # 1) Asignaciones del portal: planificadas y realizadas
    # ------------------------------------------------------
    for a in qs.order_by(
        "unidad_obra__edificio",
        "unidad_obra__vivienda",
        "tarea_obra__legacy_planta",
        "capitulo__codigo",
        "partida__codigo",
        "fecha_inicio",
        "hora_inicio",
        "empleado_id",
    )[:500]:
        start = a.fecha_inicio
        end = a.fecha_fin or a.fecha_inicio

        full_label = f"{fmt_hora(a.hora_inicio)} - {fmt_hora(a.hora_fin)}"
        compact_label = f"{fmt_hora_compacta(a.hora_inicio)}-{fmt_hora_compacta(a.hora_fin)}"
        cells = build_cells(start, end, compact_label, full_label)

        empleado_txt = str(a.empleado) if a.empleado_id else "-"
        obra_txt = display_attr(a, "pi_display_obra")
        edificio_txt = getattr(a.unidad_obra, "edificio", "") if a.unidad_obra_id else ""
        vivienda_txt = display_attr(a, "pi_display_vivienda_corta")
        planta_txt = display_attr(a, "pi_display_planta")
        capitulo_txt = display_attr(a, "pi_display_capitulo")
        partida_txt = display_attr(a, "pi_display_partida")

        if agrupacion == "vivienda":
            group_label = f"{vivienda_txt} · {planta_txt} · {edificio_txt}".strip(" ·")
        elif agrupacion == "empleado":
            group_label = empleado_txt
        elif agrupacion == "capitulo":
            group_label = capitulo_txt
        elif agrupacion == "partida":
            group_label = partida_txt
        else:
            group_label = ""

        estado_key = str(a.estado or "").upper()
        source_label = "Portal · Realizado" if estado_key == "REALIZADO" else "Portal · Planificado"

        rows.append({
            "is_group": False,
            "group_label": group_label,
            "obj": a,
            "detail_url": f"/app/planificacion-obra/asignaciones/{a.pk}/?next={gantt_next_url}",
            "source": "portal",
            "source_label": source_label,
            "empleado": empleado_txt,
            "obra": obra_txt,
            "edificio": edificio_txt,
            "vivienda": vivienda_txt,
            "planta": planta_txt,
            "capitulo": capitulo_txt,
            "partida": partida_txt,
            "estado": a.get_estado_display(),
            "estado_class": estado_classes.get(estado_key, "pendiente"),
            "cells": cells,
        })

    # ------------------------------------------------------
    # 2) Histórico real legacy
    # Mano de obra, antes de hoy, no generado desde portal.
    # ------------------------------------------------------
    qs_real = TareaRecursoReal.objects.select_related(
        "team",
        "empleado",
        "empleado__rrhh_empleado",
        "tarea_obra",
        "tarea_obra__obra",
        "unidad_obra",
        "partida",
    ).filter(
        empleado__isnull=False,
        tarea_obra__isnull=False,
        inicio_recurso_real__isnull=False,
        inicio_recurso_real__gte=fecha_desde,
        inicio_recurso_real__lte=fecha_hasta,
        inicio_recurso_real__lt=today,
        legacy_tipo_recurso__in=["M.O. ADM.", "PER. CONT.", "M.O. CONT."],
    )

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs_real = qs_real.filter(team__in=request.user.teams.all())

    # PI_PERSONAL_UNIFIED_REAL_300K_DEDUPE_V3
    if portal_real_legacy_ids:
        qs_real = qs_real.exclude(legacy_id_recurso_tarea__in=portal_real_legacy_ids)


    if obra_id.isdigit():
        qs_real = qs_real.filter(tarea_obra__obra_id=int(obra_id))

    if edificio:
        qs_real = qs_real.filter(unidad_obra__edificio=edificio)

    if vivienda:
        qs_real = qs_real.filter(unidad_obra__vivienda=vivienda)

    if planta:
        qs_real = qs_real.filter(legacy_planta=planta)

    if capitulo_id.isdigit():
        qs_real = qs_real.filter(tarea_obra__capitulo_id=int(capitulo_id))

    if partida_id.isdigit():
        qs_real = qs_real.filter(Q(partida_id=int(partida_id)) | Q(tarea_obra__partida_id=int(partida_id)))

    if empleado_id.isdigit():
        qs_real = qs_real.filter(empleado__rrhh_empleado_id=int(empleado_id))

    if estado and estado != "REALIZADO":
        qs_real = qs_real.none()

    for r in qs_real.order_by(
        "unidad_obra__edificio",
        "unidad_obra__vivienda",
        "legacy_planta",
        "legacy_capitulo",
        "legacy_partida",
        "inicio_recurso_real",
        "empleado_id",
        "id",
    )[:700]:
        start = r.inicio_recurso_real
        end = r.inicio_recurso_real

        horas = fmt_horas_gantt(r.cantidad)
        compact_label = f"{horas}h" if horas else "Real"
        full_label = f"Realizado · {horas} h" if horas else "Realizado"
        cells = build_cells(start, end, compact_label, full_label)

        empleado_txt = str(r.empleado) if r.empleado_id else "-"
        obra_obj = getattr(r.tarea_obra, "obra", None)
        obra_txt = str(obra_obj) if obra_obj else str(r.legacy_cod_obra or "-")
        edificio_txt = getattr(r.unidad_obra, "edificio", "") if r.unidad_obra_id else ""
        vivienda_txt = vivienda_label(getattr(r.unidad_obra, "vivienda", None) if r.unidad_obra_id else r.legacy_cod_vivienda)
        planta_txt = r.legacy_planta or "-"
        capitulo_txt = r.legacy_capitulo or "-"
        partida_txt = (
            getattr(getattr(r, "partida", None), "nombre", "")
            or getattr(getattr(getattr(r, "tarea_obra", None), "partida", None), "nombre", "")
            or getattr(r, "legacy_partida", "")
            or "-"
        )

        if agrupacion == "vivienda":
            group_label = f"{vivienda_txt} · {planta_txt} · {edificio_txt}".strip(" ·")
        elif agrupacion == "empleado":
            group_label = empleado_txt
        elif agrupacion == "capitulo":
            group_label = capitulo_txt
        elif agrupacion == "partida":
            group_label = partida_txt
        else:
            group_label = ""

        rows.append({
            "is_group": False,
            "group_label": group_label,
            "obj": None,
            "detail_url": f"/app/planificacion-obra/realizados/{r.pk}/?next={gantt_next_url}",
            "source": "historico",
            "source_label": "Realizado",
            "empleado": empleado_txt,
            "obra": obra_txt,
            "edificio": edificio_txt,
            "vivienda": vivienda_txt,
            "planta": planta_txt,
            "capitulo": capitulo_txt,
            "partida": partida_txt,
            "estado": "Realizado",
            "estado_class": "completada",
            "cells": cells,
        })


    # Preparar filas finales para render.
    # Si hay agrupación, se insertan filas cabecera reales antes de cada bloque.
    render_rows = rows

    if agrupacion != "asignacion":
        base_rows = sorted(rows, key=lambda row: (
            str(row.get("group_label") or "Sin grupo"),
            str(row.get("vivienda") or ""),
            str(row.get("planta") or ""),
            str(row.get("empleado") or ""),
            str(row.get("capitulo") or ""),
            str(row.get("partida") or ""),
        ))

        render_rows = []
        last_group = None

        for row in base_rows:
            label = row.get("group_label") or "Sin grupo"

            if label != last_group:
                render_rows.append({
                    "is_group": True,
                    "group_label": label,
                })
                last_group = label

            render_rows.append(row)

    obras = ObraPlanificacion.objects.all().order_by("codigo", "id")

    # Opciones relacionadas para los filtros del Gantt.
    # No deben salir edificios/viviendas/partidas globales si ya hay una obra seleccionada.
    option_unidades = UnidadObra.objects.all()
    option_tareas = TareaObra.objects.select_related("unidad_obra", "capitulo", "partida")

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        user_teams = request.user.teams.all()
        option_unidades = option_unidades.filter(team__in=user_teams)
        option_tareas = option_tareas.filter(team__in=user_teams)

    if obra_id.isdigit():
        option_unidades = option_unidades.filter(obra_id=int(obra_id))
        option_tareas = option_tareas.filter(obra_id=int(obra_id))

    edificios = sorted(set(
        option_unidades
        .exclude(edificio__isnull=True)
        .exclude(edificio="")
        .values_list("edificio", flat=True)
    ))

    if edificio:
        option_unidades = option_unidades.filter(edificio=edificio)
        option_tareas = option_tareas.filter(unidad_obra__edificio=edificio)

    viviendas_qs = (
        option_unidades
        .exclude(vivienda__isnull=True)
        .exclude(vivienda="")
        .values_list("vivienda", flat=True)
    )

    def vivienda_sort_key(v):
        s = str(v)
        return (0, int(s)) if s.isdigit() else (1, s)

    viviendas = sorted(set(viviendas_qs), key=vivienda_sort_key)

    if vivienda:
        option_unidades = option_unidades.filter(vivienda=vivienda)
        option_tareas = option_tareas.filter(unidad_obra__vivienda=vivienda)

    plantas = sorted(set(
        option_tareas
        .exclude(legacy_planta__isnull=True)
        .exclude(legacy_planta="")
        .values_list("legacy_planta", flat=True)
    ))

    if planta:
        option_tareas = option_tareas.filter(legacy_planta=planta)

    capitulo_ids = (
        option_tareas
        .exclude(capitulo_id__isnull=True)
        .values_list("capitulo_id", flat=True)
        .distinct()
    )
    capitulos = CapituloCatalogo.objects.filter(id__in=capitulo_ids).order_by("codigo", "orden", "id")

    if capitulo_id.isdigit():
        option_tareas = option_tareas.filter(capitulo_id=int(capitulo_id))

    partida_ids = (
        option_tareas
        .exclude(partida_id__isnull=True)
        .values_list("partida_id", flat=True)
        .distinct()
    )
    partidas = (
        PartidaCatalogo.objects
        .filter(id__in=partida_ids)
        .select_related("capitulo")
        .order_by("codigo", "id")
    )

    empleados = AsignacionObraForm().fields["empleado"].queryset
    estados = AsignacionObra._meta.get_field("estado").choices

    agrupacion_labels = {
        "asignacion": "Sin agrupar",
        "vivienda": "Vivienda",
        "empleado": "Empleado",
        "capitulo": "Capítulo",
        "partida": "Partida",
    }

    # ASIGNACIONES_GANTT_FILTRO_RESUMEN_FIX_V1
    # Antes se enviaba filtro_resumen al contexto sin definirlo.
    filtro_resumen_partes = [
        (
            f"{fecha_desde.strftime('%d/%m/%Y')}"
            f" – {fecha_hasta.strftime('%d/%m/%Y')}"
        )
    ]

    if obra_id:
        filtro_resumen_partes.append(f"Obra {obra_id}")
    if edificio:
        filtro_resumen_partes.append(f"Edificio/Fase {edificio}")
    if vivienda:
        filtro_resumen_partes.append(f"Vivienda {vivienda}")
    if planta:
        filtro_resumen_partes.append(f"Planta {planta}")
    if capitulo_id:
        filtro_resumen_partes.append(f"Capítulo {capitulo_id}")
    if partida_id:
        filtro_resumen_partes.append(f"Partida {partida_id}")
    if empleado_id:
        filtro_resumen_partes.append(f"Empleado {empleado_id}")
    if estado:
        filtro_resumen_partes.append(f"Estado {estado}")

    filtro_resumen = " · ".join(filtro_resumen_partes)

    return render(request, "planificacion_obra/asignaciones_gantt.html", {
        "rows": render_rows,
        "agrupacion_label": agrupacion_labels.get(agrupacion, "Sin agrupar"),
        "days": days,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "obras": obras,
        "edificios": edificios,
        "viviendas": viviendas,
        "plantas": plantas,
        "capitulos": capitulos,
        "partidas": partidas,
        "empleados": empleados,
        "estados": estados,
        "filtro_resumen": filtro_resumen,
        "filters": {
            "obra": obra_id,
            "edificio": edificio,
            "vivienda": vivienda,
            "planta": planta,
            "capitulo": capitulo_id,
            "partida": partida_id,
            "empleado": empleado_id,
            "estado": estado,
            "agrupacion": agrupacion,
              "vista": "gantt" if vista_gantt else "",
        },
    })

# ---------------------------------------------------------------------
# Informe imprimible de planificación de asignaciones
# ---------------------------------------------------------------------
@login_required

def asignaciones_informe(request):
    from datetime import date, datetime, timedelta
    from django.apps import apps
    from django.db.models import Q
    from django.shortcuts import render
    from django.utils import timezone

    AsignacionObra = apps.get_model("planificacion_obra", "AsignacionObra")
    TareaRecursoReal = apps.get_model("planificacion_obra", "TareaRecursoReal")
    ObraPlanificacion = apps.get_model("planificacion_obra", "ObraPlanificacion")
    UnidadObra = apps.get_model("planificacion_obra", "UnidadObra")
    TareaObra = apps.get_model("planificacion_obra", "TareaObra")
    CapituloCatalogo = apps.get_model("planificacion_obra", "CapituloCatalogo")
    PartidaCatalogo = apps.get_model("planificacion_obra", "PartidaCatalogo")

    from .forms import AsignacionObraForm

    today = timezone.localdate()

    def parse_date(value, default):
        try:
            return date.fromisoformat(value)
        except Exception:
            return default

    # ASIGNACIONES_INFORME_RANGO_COMPLETO_V1
    #
    # Informe de Producción / Asignación:
    # - "Hasta" por defecto es la fecha actual.
    # - No existe límite máximo de días.
    # - Un rango solicitado explícitamente se respeta completo.
    #
    # El límite temporal del Gantt es independiente y no se modifica.
    fecha_desde = parse_date(request.GET.get("desde"), today)
    fecha_hasta = parse_date(request.GET.get("hasta"), today)

    if fecha_hasta < fecha_desde:
        fecha_hasta = fecha_desde

    obra_id = request.GET.get("obra") or ""
    edificio = request.GET.get("edificio") or ""
    vivienda = request.GET.get("vivienda") or ""
    planta = request.GET.get("planta") or ""
    capitulo_id = request.GET.get("capitulo") or ""
    partida_id = request.GET.get("partida") or ""
    empleado_id = request.GET.get("empleado") or ""
    estado = request.GET.get("estado") or ""

    def by_team(qs):
        if not request.user.is_superuser and hasattr(request.user, "teams"):
            return qs.filter(team__in=request.user.teams.all())
        return qs

    def display_attr(obj, attr, default="-"):
        try:
            value = getattr(obj, attr)
            return value if value not in ("", None) else default
        except Exception:
            return default

    def fmt_hora(h):
        return h.strftime("%H:%M") if h else ""

    def horas_asignacion(a):
        if not a.hora_inicio or not a.hora_fin:
            return 0.0

        start_dt = datetime.combine(a.fecha_inicio, a.hora_inicio)
        end_date = a.fecha_fin or a.fecha_inicio
        end_dt = datetime.combine(end_date, a.hora_fin)

        if end_dt < start_dt:
            return 0.0

        return round((end_dt - start_dt).total_seconds() / 3600, 2)

    def vivienda_label(cod):
        cod = str(cod or "").strip()
        if not cod or cod == "0":
            return "Obra"
        return f"Viv. {cod}"

    rows = []
    empleados_set = set()
    viviendas_set = set()
    total_horas = 0.0

    # ------------------------------------------------------
    # 1) Asignaciones portal
    # ------------------------------------------------------
    qs = AsignacionObra.objects.select_related(
        "team",
        "empleado",
        "tarea_obra",
        "unidad_obra",
        "capitulo",
        "partida",
    )

    qs = by_team(qs)

    qs = qs.filter(fecha_inicio__lte=fecha_hasta).filter(
        Q(fecha_fin__gte=fecha_desde) |
        Q(fecha_fin__isnull=True, fecha_inicio__gte=fecha_desde)
    )

    if obra_id.isdigit():
        qs = qs.filter(tarea_obra__obra_id=int(obra_id))

    if edificio:
        qs = qs.filter(unidad_obra__edificio=edificio)

    if vivienda:
        qs = qs.filter(unidad_obra__vivienda=vivienda)

    if planta:
        qs = qs.filter(tarea_obra__legacy_planta=planta)

    if capitulo_id.isdigit():
        qs = qs.filter(capitulo_id=int(capitulo_id))

    if partida_id.isdigit():
        qs = qs.filter(partida_id=int(partida_id))

    if empleado_id.isdigit():
        qs = qs.filter(empleado_id=int(empleado_id))

    if estado:
        qs = qs.filter(estado=estado)

    # PI_PERSONAL_UNIFIED_REAL_300K_DEDUPE_V3
    portal_real_legacy_ids = {
        300000 + int(pk)
        for pk in qs.values_list("id", flat=True)
    }


    # ASIGNACIONES_INFORME_FILAS_COMPLETAS_SCROLL_V20
    # El rango solicitado se representa completo; sin cortes por número de filas.
    for a in qs.order_by(
        "fecha_inicio",
        "hora_inicio",
        "unidad_obra__edificio",
        "unidad_obra__vivienda",
        "tarea_obra__legacy_planta",
        "empleado_id",
        "capitulo__codigo",
        "partida__codigo",
    ):
        horas = horas_asignacion(a)
        total_horas += horas

        if a.empleado_id:
            empleados_set.add(f"rrhh-{a.empleado_id}")

        if a.unidad_obra_id:
            viviendas_set.add(f"unidad-{a.unidad_obra_id}")

        origen = "Portal · Realizado" if str(a.estado or "").upper() == "REALIZADO" else "Portal · Planificado"

        rows.append({
            "source": "portal",
            "obj": a,
            "coste": "",
            "fecha": a.fecha_inicio,
            "fecha_fin": a.fecha_fin,
            "horario": f"{fmt_hora(a.hora_inicio)} - {fmt_hora(a.hora_fin)}",
            "horas": horas,
            "empleado": str(a.empleado) if a.empleado_id else "-",
            "obra": display_attr(a, "pi_display_obra"),
            "edificio": getattr(a.unidad_obra, "edificio", "") if a.unidad_obra_id else "",
            "vivienda": display_attr(a, "pi_display_vivienda_corta"),
            "planta": display_attr(a, "pi_display_planta"),
            "capitulo": display_attr(a, "pi_display_capitulo"),
            "partida": display_attr(a, "pi_display_partida"),
            "estado": a.get_estado_display(),
            "origen": origen,
        })

    # ------------------------------------------------------
    # 2) Histórico real legacy
    # ------------------------------------------------------
    qs_real = TareaRecursoReal.objects.select_related(
        "team",
        "empleado",
        "empleado__rrhh_empleado",
        "tarea_obra",
        "tarea_obra__obra",
        "unidad_obra",
        "partida",
    ).filter(
        empleado__isnull=False,
        tarea_obra__isnull=False,
        inicio_recurso_real__isnull=False,
        inicio_recurso_real__gte=fecha_desde,
        inicio_recurso_real__lte=fecha_hasta,
        inicio_recurso_real__lt=today,
        legacy_tipo_recurso__in=["M.O. ADM.", "PER. CONT.", "M.O. CONT."],
    )

    qs_real = by_team(qs_real)

    # PI_PERSONAL_UNIFIED_REAL_300K_DEDUPE_V3
    if portal_real_legacy_ids:
        qs_real = qs_real.exclude(legacy_id_recurso_tarea__in=portal_real_legacy_ids)


    if obra_id.isdigit():
        qs_real = qs_real.filter(tarea_obra__obra_id=int(obra_id))

    if edificio:
        qs_real = qs_real.filter(unidad_obra__edificio=edificio)

    if vivienda:
        qs_real = qs_real.filter(unidad_obra__vivienda=vivienda)

    if planta:
        qs_real = qs_real.filter(legacy_planta=planta)

    if capitulo_id.isdigit():
        qs_real = qs_real.filter(tarea_obra__capitulo_id=int(capitulo_id))

    if partida_id.isdigit():
        qs_real = qs_real.filter(Q(partida_id=int(partida_id)) | Q(tarea_obra__partida_id=int(partida_id)))

    if empleado_id.isdigit():
        qs_real = qs_real.filter(empleado__rrhh_empleado_id=int(empleado_id))

    if estado and estado != "REALIZADO":
        qs_real = qs_real.none()

    for r in qs_real.order_by(
        "inicio_recurso_real",
        "unidad_obra__edificio",
        "unidad_obra__vivienda",
        "legacy_planta",
        "empleado_id",
        "legacy_capitulo",
        "legacy_partida",
        "id",
    ):
        horas = float(r.cantidad or 0)
        total_horas += horas

        if r.empleado_id:
            rrhh_id = getattr(r.empleado, "rrhh_empleado_id", None)
            empleados_set.add(f"rrhh-{rrhh_id}" if rrhh_id else f"empleadoobra-{r.empleado_id}")

        if r.unidad_obra_id:
            viviendas_set.add(f"unidad-{r.unidad_obra_id}")
        elif r.legacy_cod_vivienda:
            viviendas_set.add(f"legacy-{r.legacy_cod_vivienda}")

        obra_obj = getattr(r.tarea_obra, "obra", None)
        obra_txt = str(obra_obj) if obra_obj else str(r.legacy_cod_obra or "-")
        coste = round(float(r.cantidad or 0) * float(r.precio_unidad or 0), 2)

        rows.append({
            "source": "historico",
            "obj": None,
            "coste": coste,
            "fecha": r.inicio_recurso_real,
            "fecha_fin": r.fin_recurso_real or r.inicio_recurso_real,
            "horario": "",
            "horas": round(horas, 2),
            "empleado": str(r.empleado) if r.empleado_id else "-",
            "obra": obra_txt,
            "edificio": getattr(r.unidad_obra, "edificio", "") if r.unidad_obra_id else "",
            "vivienda": vivienda_label(getattr(r.unidad_obra, "vivienda", None) if r.unidad_obra_id else r.legacy_cod_vivienda),
            "planta": r.legacy_planta or "-",
            "capitulo": r.legacy_capitulo or "-",
            "partida": (
                getattr(getattr(r, "partida", None), "nombre", "")
                or getattr(getattr(getattr(r, "tarea_obra", None), "partida", None), "nombre", "")
                or getattr(r, "legacy_partida", "")
                or "-"
            ),
            "partida_codigo": (
                getattr(getattr(r, "partida", None), "codigo", "")
                or getattr(getattr(getattr(r, "tarea_obra", None), "partida", None), "codigo", "")
                or getattr(r, "legacy_partida", "")
                or ""
            ),
            "partida_title": (
                (
                    (getattr(getattr(r, "partida", None), "codigo", "") or getattr(getattr(getattr(r, "tarea_obra", None), "partida", None), "codigo", "") or getattr(r, "legacy_partida", "") or "")
                    + " · "
                    + (getattr(getattr(r, "partida", None), "nombre", "") or getattr(getattr(getattr(r, "tarea_obra", None), "partida", None), "nombre", "") or getattr(r, "legacy_partida", "") or "-")
                ).strip(" ·")
            ),
            "estado": "Realizado",
            "origen": "Realizado",
        })

    # PI_INFORME_PORTAL_REAL300K_LINE_V6
    # Normalización final antes de ordenar:
    # en asignaciones portal REALIZADO, si existe TareaRecursoReal 300000 + asignacion.id,
    # el informe usa el EmpleadoObra, horas e importe de ese real.
    portal_asig_ids_para_real = []
    for row in rows:
        obj = row.get("obj")
        if (
            row.get("source") == "portal"
            and obj is not None
            and getattr(obj, "id", None)
            and str(getattr(obj, "estado", "") or "").upper() == "REALIZADO"
        ):
            portal_asig_ids_para_real.append(int(obj.id))

    reales_portal_por_asignacion = {}
    if portal_asig_ids_para_real:
        legacy_ids_portal = [300000 + pk for pk in portal_asig_ids_para_real]
        for real_portal in (
            TareaRecursoReal.objects
            .filter(legacy_id_recurso_tarea__in=legacy_ids_portal)
            .select_related("empleado", "partida", "tarea_obra", "tarea_obra__partida")
        ):
            try:
                asignacion_id = int(real_portal.legacy_id_recurso_tarea or 0) - 300000
            except Exception:
                asignacion_id = 0
            if asignacion_id > 0:
                reales_portal_por_asignacion[asignacion_id] = real_portal

    for row in rows:
        row["horario"] = ""

        obj = row.get("obj")
        if row.get("source") != "portal" or obj is None or not getattr(obj, "id", None):
            continue

        real_portal = reales_portal_por_asignacion.get(int(obj.id))
        if not real_portal:
            continue

        horas_real = float(
            getattr(real_portal, "cantidad", None)
            or getattr(real_portal, "horas_reales", None)
            or getattr(real_portal, "horas", None)
            or 0
        )
        precio_real = float(getattr(real_portal, "precio_unidad", None) or 0)
        coste_real = float(getattr(real_portal, "costo_recurso_real", None) or 0)
        if not coste_real:
            coste_real = horas_real * precio_real

        partida_obj = (
            getattr(real_portal, "partida", None)
            or getattr(getattr(real_portal, "tarea_obra", None), "partida", None)
        )

        row["empleado"] = (
            str(real_portal.empleado)
            if getattr(real_portal, "empleado_id", None)
            else row.get("empleado", "-")
        )
        row["horas"] = round(horas_real, 2)
        row["coste"] = round(coste_real, 2)
        row["capitulo"] = getattr(real_portal, "legacy_capitulo", "") or row.get("capitulo", "-")
        row["partida"] = (
            getattr(partida_obj, "nombre", "")
            or getattr(real_portal, "legacy_partida", "")
            or row.get("partida", "-")
        )
        row["partida_codigo"] = (
            getattr(partida_obj, "codigo", "")
            or getattr(real_portal, "legacy_partida", "")
            or ""
        )
        row["partida_title"] = (
            (row.get("partida_codigo", "") + " · " + row.get("partida", "")).strip(" ·")
            if row.get("partida_codigo")
            else row.get("partida", "-")
        )

    total_horas = round(sum(float(row.get("horas") or 0) for row in rows), 2)
    empleados_set = {
        str(row.get("empleado"))
        for row in rows
        if row.get("empleado") not in ("", None, "-")
    }

    rows.sort(key=lambda row: (
        row.get("fecha") or date.min,
        str(row.get("empleado") or ""),
        str(row.get("vivienda") or ""),
        str(row.get("planta") or ""),
        str(row.get("capitulo") or ""),
        str(row.get("partida") or ""),
    ))

    # ------------------------------------------------------
    # Opciones relacionadas para filtros.
    # ------------------------------------------------------
    option_unidades = UnidadObra.objects.all()
    option_tareas = TareaObra.objects.select_related("unidad_obra", "capitulo", "partida")

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        user_teams = request.user.teams.all()
        option_unidades = option_unidades.filter(team__in=user_teams)
        option_tareas = option_tareas.filter(team__in=user_teams)

    if obra_id.isdigit():
        option_unidades = option_unidades.filter(obra_id=int(obra_id))
        option_tareas = option_tareas.filter(obra_id=int(obra_id))

    edificios = sorted(set(
        option_unidades
        .exclude(edificio__isnull=True)
        .exclude(edificio="")
        .values_list("edificio", flat=True)
    ))

    if edificio:
        option_unidades = option_unidades.filter(edificio=edificio)
        option_tareas = option_tareas.filter(unidad_obra__edificio=edificio)

    viviendas_qs = (
        option_unidades
        .exclude(vivienda__isnull=True)
        .exclude(vivienda="")
        .values_list("vivienda", flat=True)
    )

    def vivienda_sort_key(v):
        s = str(v)
        return (0, int(s)) if s.isdigit() else (1, s)

    viviendas = sorted(set(viviendas_qs), key=vivienda_sort_key)

    if vivienda:
        option_unidades = option_unidades.filter(vivienda=vivienda)
        option_tareas = option_tareas.filter(unidad_obra__vivienda=vivienda)

    plantas = sorted(set(
        option_tareas
        .exclude(legacy_planta__isnull=True)
        .exclude(legacy_planta="")
        .values_list("legacy_planta", flat=True)
    ))

    if planta:
        option_tareas = option_tareas.filter(legacy_planta=planta)

    capitulo_ids = (
        option_tareas
        .exclude(capitulo_id__isnull=True)
        .values_list("capitulo_id", flat=True)
        .distinct()
    )

    capitulos = CapituloCatalogo.objects.filter(id__in=capitulo_ids).order_by("codigo", "orden", "id")

    if capitulo_id.isdigit():
        option_tareas = option_tareas.filter(capitulo_id=int(capitulo_id))

    partida_ids = (
        option_tareas
        .exclude(partida_id__isnull=True)
        .values_list("partida_id", flat=True)
        .distinct()
    )

    partidas = (
        PartidaCatalogo.objects
        .filter(id__in=partida_ids)
        .select_related("capitulo")
        .order_by("codigo", "id")
    )

    obras = ObraPlanificacion.objects.all().order_by("codigo", "id")
    if not request.user.is_superuser and hasattr(request.user, "teams"):
        obras = obras.filter(team__in=request.user.teams.all())

    empleados = AsignacionObraForm(request_user=request.user).fields["empleado"].queryset
    estados = AsignacionObra._meta.get_field("estado").choices

    querystring = request.GET.urlencode()


    # FIX_ASIGNACIONES_INFORME_PROFESIONAL_V7
    # Normalización visual final para informe compacto:
    # - Capítulo: si viene vacío en históricos, se deriva desde partida_codigo (16.016 -> 16)
    # - Trabajo: una sola etiqueta compacta
    # - Importe/Horas: formato listo para tabla
    def _pi_clean(value):
        value = "" if value is None else str(value).strip()
        return "" if value in ("", "-", "None") else value

    def _pi_money(value):
        try:
            return f"{float(value):.2f}".replace(".", ",") + " €"
        except Exception:
            return "0,00 €"

    def _pi_hours(value):
        try:
            return f"{float(value):.2f}".replace(".", ",")
        except Exception:
            return "0,00"

    for _row in rows:
        if not isinstance(_row, dict):
            continue

        _capitulo = _pi_clean(_row.get("capitulo"))
        _partida_codigo = _pi_clean(_row.get("partida_codigo"))
        _partida_title = _pi_clean(_row.get("partida_title"))

        if not _capitulo:
            if _partida_codigo and "." in _partida_codigo:
                _capitulo = _partida_codigo.split(".", 1)[0].strip()
            elif _partida_codigo:
                _capitulo = _partida_codigo
            elif _partida_title and "." in _partida_title:
                _capitulo = _partida_title.split(".", 1)[0].strip()

        _row["capitulo_display"] = _capitulo or "-"
        _row["trabajo_display"] = _partida_title or _pi_clean(_row.get("partida")) or "-"
        _row["horas_display"] = _pi_hours(_row.get("horas"))
        _row["importe_display"] = _pi_money(_row.get("coste"))


    # FIX_ASIGNACIONES_INFORME_FILTROS_CAPITULO_V9
    # Resumen visible de filtros + nombre real de capítulo para pantalla/impresión.
    def _v9_clean(value):
        value = "" if value is None else str(value).strip()
        return "" if value in ("", "-", "None") else value

    def _v9_norm_code(value):
        value = _v9_clean(value).upper()
        value = value.replace("CAP.", "").replace("CAPITULO", "").replace("CAPÍTULO", "")
        value = value.replace("C-", "").replace("C ", "")
        if value.startswith("C") and len(value) <= 4:
            value = value[1:]
        value = value.split("·", 1)[0].strip()
        value = value.split(" ", 1)[0].strip()
        if "." in value:
            value = value.split(".", 1)[0].strip()
        return value.zfill(2) if value.isdigit() else value

    def _v9_get_label(obj, fallback=""):
        if not obj:
            return fallback
        codigo = _v9_clean(getattr(obj, "codigo", ""))
        nombre = (
            _v9_clean(getattr(obj, "nombre", "")) or
            _v9_clean(getattr(obj, "descripcion", "")) or
            _v9_clean(str(obj))
        )
        if codigo and nombre and codigo not in nombre:
            return f"{codigo} · {nombre}"
        return nombre or codigo or fallback

    # Mapa de capítulos por código normalizado.
    capitulo_map = {}
    try:
        cap_qs = by_team(CapituloCatalogo.objects.all())
    except Exception:
        cap_qs = CapituloCatalogo.objects.all()

    for _cap in cap_qs:
        _codigo = _v9_clean(getattr(_cap, "codigo", ""))
        _label = _v9_get_label(_cap)
        for _key in {_codigo, _v9_norm_code(_codigo), _codigo.replace("C", "", 1) if _codigo.startswith("C") else _codigo}:
            _key = _v9_norm_code(_key)
            if _key:
                capitulo_map[_key] = _label

    for _row in rows:
        if not isinstance(_row, dict):
            continue

        _raw_cap = _v9_clean(_row.get("capitulo"))
        _partida_codigo = _v9_clean(_row.get("partida_codigo"))
        _partida_title = _v9_clean(_row.get("partida_title"))
        _partida = _v9_clean(_row.get("partida"))

        _cap_key = _v9_norm_code(_raw_cap)
        if not _cap_key and _partida_codigo:
            _cap_key = _v9_norm_code(_partida_codigo)
        if not _cap_key and _partida_title:
            _cap_key = _v9_norm_code(_partida_title)
        if not _cap_key and _partida:
            _cap_key = _v9_norm_code(_partida)

        _row["capitulo_display"] = capitulo_map.get(_cap_key) or _raw_cap or _cap_key or "-"
        _row["trabajo_display"] = _partida_title or _partida or "-"

    def _v9_selected(qs, pk):
        try:
            if str(pk).isdigit():
                return qs.filter(pk=int(pk)).first()
        except Exception:
            return None
        return None

    filtro_resumen = []
    filtro_resumen.append(("Periodo", f"{fecha_desde.strftime('%d/%m/%Y')} — {fecha_hasta.strftime('%d/%m/%Y')}"))

    if obra_id.isdigit():
        _obra = ObraPlanificacion.objects.filter(pk=int(obra_id)).first()
        filtro_resumen.append(("Obra", _v9_get_label(_obra, obra_id)))

    if edificio:
        filtro_resumen.append(("Edificio / Fase", edificio))

    if vivienda:
        filtro_resumen.append(("Vivienda", vivienda_label(vivienda)))

    if planta:
        filtro_resumen.append(("Planta", planta))

    if capitulo_id.isdigit():
        _cap = CapituloCatalogo.objects.filter(pk=int(capitulo_id)).first()
        filtro_resumen.append(("Capítulo", _v9_get_label(_cap, capitulo_id)))

    if partida_id.isdigit():
        _partida = PartidaCatalogo.objects.filter(pk=int(partida_id)).first()
        filtro_resumen.append(("Partida", _v9_get_label(_partida, partida_id)))

    if empleado_id.isdigit():
        try:
            _empleado = AsignacionObraForm().fields["empleado"].queryset.filter(pk=int(empleado_id)).first()
            filtro_resumen.append(("Empleado", str(_empleado) if _empleado else empleado_id))
        except Exception:
            filtro_resumen.append(("Empleado", empleado_id))

    if estado:
        filtro_resumen.append(("Estado", estado))


    # FIX_ASIGNACIONES_INFORME_FINAL_V11
    # Última normalización antes del render:
    # - filtros aplicados visibles en pantalla e impresión
    # - nombre real de capítulo en tabla, no solo código
    def _v11_clean(value):
        value = "" if value is None else str(value).strip()
        return "" if value in ("", "-", "None") else value

    def _v11_norm_cap(value):
        value = _v11_clean(value).upper()
        value = value.replace("CAPÍTULO", "").replace("CAPITULO", "").replace("CAP.", "")
        value = value.replace("C-", "").replace("C ", "")
        value = value.split("·", 1)[0].strip()
        value = value.split(" ", 1)[0].strip()
        if "." in value:
            value = value.split(".", 1)[0].strip()
        if value.startswith("C") and value[1:].isdigit():
            value = value[1:]
        return value.zfill(2) if value.isdigit() else value

    def _v11_obj_label(obj, fallback=""):
        if not obj:
            return fallback
        codigo = _v11_clean(getattr(obj, "codigo", ""))
        nombre = (
            _v11_clean(getattr(obj, "nombre", "")) or
            _v11_clean(getattr(obj, "descripcion", "")) or
            _v11_clean(str(obj))
        )
        if codigo and nombre and codigo not in nombre:
            return f"{codigo} · {nombre}"
        return nombre or codigo or fallback

    capitulo_map_v11 = {}
    try:
        cap_qs_v11 = CapituloCatalogo.objects.all()
        for _cap in cap_qs_v11:
            _codigo = _v11_clean(getattr(_cap, "codigo", ""))
            _label = _v11_obj_label(_cap)
            for _key in (_codigo, _codigo.replace("C", "", 1), str(_cap)):
                _key = _v11_norm_cap(_key)
                if _key:
                    capitulo_map_v11[_key] = _label
    except Exception:
        capitulo_map_v11 = {}

    for _row in rows:
        if not isinstance(_row, dict):
            continue

        _partida_codigo = _v11_clean(_row.get("partida_codigo"))
        _partida_title = _v11_clean(_row.get("partida_title"))
        _partida = _v11_clean(_row.get("partida"))
        _cap_raw = _v11_clean(_row.get("capitulo_display")) or _v11_clean(_row.get("capitulo"))

        _cap_key = (
            _v11_norm_cap(_partida_codigo) or
            _v11_norm_cap(_partida_title) or
            _v11_norm_cap(_partida) or
            _v11_norm_cap(_cap_raw)
        )

        _row["capitulo_display"] = capitulo_map_v11.get(_cap_key) or _cap_raw or _cap_key or "-"
        _row["trabajo_display"] = _partida_title or _partida or _v11_clean(_row.get("trabajo_display")) or "-"

    filtro_resumen = []

    filtro_resumen.append((
        "Periodo",
        f"{fecha_desde.strftime('%d/%m/%Y')} — {fecha_hasta.strftime('%d/%m/%Y')}"
    ))

    if obra_id.isdigit():
        try:
            _obra = ObraPlanificacion.objects.filter(pk=int(obra_id)).first()
            filtro_resumen.append(("Obra", _v11_obj_label(_obra, obra_id)))
        except Exception:
            filtro_resumen.append(("Obra", obra_id))

    if edificio:
        filtro_resumen.append(("Edificio / Fase", edificio))

    if vivienda:
        try:
            filtro_resumen.append(("Vivienda", vivienda_label(vivienda)))
        except Exception:
            filtro_resumen.append(("Vivienda", vivienda))

    if planta:
        filtro_resumen.append(("Planta", planta))

    if capitulo_id.isdigit():
        try:
            _cap = CapituloCatalogo.objects.filter(pk=int(capitulo_id)).first()
            filtro_resumen.append(("Capítulo", _v11_obj_label(_cap, capitulo_id)))
        except Exception:
            filtro_resumen.append(("Capítulo", capitulo_id))

    if partida_id.isdigit():
        try:
            _part = PartidaCatalogo.objects.filter(pk=int(partida_id)).first()
            filtro_resumen.append(("Partida", _v11_obj_label(_part, partida_id)))
        except Exception:
            filtro_resumen.append(("Partida", partida_id))

    if empleado_id.isdigit():
        filtro_resumen.append(("Empleado", empleado_id))

    if estado:
        filtro_resumen.append(("Estado", estado))



    # FIX_ASIGNACIONES_INFORME_FILTROS_V12
    # Resumen robusto de filtros aplicados para pantalla e impresión.
    def _v12_clean(value):
        value = "" if value is None else str(value).strip()
        return "" if value in ("", "-", "None") else value

    def _v12_label_obj(obj, fallback=""):
        if not obj:
            return fallback
        codigo = _v12_clean(getattr(obj, "codigo", ""))
        nombre = (
            _v12_clean(getattr(obj, "nombre", "")) or
            _v12_clean(getattr(obj, "descripcion", "")) or
            _v12_clean(str(obj))
        )
        if codigo and nombre and codigo not in nombre:
            return f"{codigo} · {nombre}"
        return nombre or codigo or fallback

    applied_filters_pairs_v12 = []
    applied_filters_pairs_v12.append((
        "Periodo",
        f"{fecha_desde.strftime('%d/%m/%Y')} — {fecha_hasta.strftime('%d/%m/%Y')}"
    ))

    if obra_id.isdigit():
        try:
            _obra_v12 = ObraPlanificacion.objects.filter(pk=int(obra_id)).first()
            applied_filters_pairs_v12.append(("Obra", _v12_label_obj(_obra_v12, obra_id)))
        except Exception:
            applied_filters_pairs_v12.append(("Obra", obra_id))

    if edificio:
        applied_filters_pairs_v12.append(("Edificio / Fase", edificio))

    if vivienda:
        try:
            applied_filters_pairs_v12.append(("Vivienda", vivienda_label(vivienda)))
        except Exception:
            applied_filters_pairs_v12.append(("Vivienda", vivienda))

    if planta:
        applied_filters_pairs_v12.append(("Planta", planta))

    if capitulo_id.isdigit():
        try:
            _cap_v12 = CapituloCatalogo.objects.filter(pk=int(capitulo_id)).first()
            applied_filters_pairs_v12.append(("Capítulo", _v12_label_obj(_cap_v12, capitulo_id)))
        except Exception:
            applied_filters_pairs_v12.append(("Capítulo", capitulo_id))

    if partida_id.isdigit():
        try:
            _part_v12 = PartidaCatalogo.objects.filter(pk=int(partida_id)).first()
            applied_filters_pairs_v12.append(("Partida", _v12_label_obj(_part_v12, partida_id)))
        except Exception:
            applied_filters_pairs_v12.append(("Partida", partida_id))

    if empleado_id.isdigit():
        applied_filters_pairs_v12.append(("Empleado", empleado_id))

    if estado:
        applied_filters_pairs_v12.append(("Estado", estado))



    # FIX_ASIGNACIONES_INFORME_FILTROS_TEMPLATE_V13
    # Filtros aplicados visibles en pantalla e impresión.
    def _v13_clean(value):
        value = "" if value is None else str(value).strip()
        return "" if value in ("", "-", "None") else value

    def _v13_obj_label(obj, fallback=""):
        if not obj:
            return fallback
        codigo = _v13_clean(getattr(obj, "codigo", ""))
        nombre = (
            _v13_clean(getattr(obj, "nombre", "")) or
            _v13_clean(getattr(obj, "descripcion", "")) or
            _v13_clean(str(obj))
        )
        if codigo and nombre and codigo not in nombre:
            return f"{codigo} · {nombre}"
        return nombre or codigo or fallback

    applied_filters_pairs_v13 = []
    applied_filters_pairs_v13.append((
        "Periodo",
        f"{fecha_desde.strftime('%d/%m/%Y')} — {fecha_hasta.strftime('%d/%m/%Y')}"
    ))

    if obra_id.isdigit():
        try:
            _obra_v13 = ObraPlanificacion.objects.filter(pk=int(obra_id)).first()
            applied_filters_pairs_v13.append(("Obra", _v13_obj_label(_obra_v13, obra_id)))
        except Exception:
            applied_filters_pairs_v13.append(("Obra", obra_id))

    if edificio:
        applied_filters_pairs_v13.append(("Edificio / Fase", edificio))

    if vivienda:
        try:
            applied_filters_pairs_v13.append(("Vivienda", vivienda_label(vivienda)))
        except Exception:
            applied_filters_pairs_v13.append(("Vivienda", vivienda))

    if planta:
        applied_filters_pairs_v13.append(("Planta", planta))

    if capitulo_id.isdigit():
        try:
            _cap_v13 = CapituloCatalogo.objects.filter(pk=int(capitulo_id)).first()
            applied_filters_pairs_v13.append(("Capítulo", _v13_obj_label(_cap_v13, capitulo_id)))
        except Exception:
            applied_filters_pairs_v13.append(("Capítulo", capitulo_id))

    if partida_id.isdigit():
        try:
            _part_v13 = PartidaCatalogo.objects.filter(pk=int(partida_id)).first()
            applied_filters_pairs_v13.append(("Partida", _v13_obj_label(_part_v13, partida_id)))
        except Exception:
            applied_filters_pairs_v13.append(("Partida", partida_id))

    if empleado_id.isdigit():
        applied_filters_pairs_v13.append(("Empleado", empleado_id))

    if estado:
        applied_filters_pairs_v13.append(("Estado", estado))



    # FIX_ASIGNACIONES_INFORME_PRINT_FILTERS_V14
    # Línea resumen visible en encabezado de pantalla e impresión.
    def _v14_clean(value):
        value = "" if value is None else str(value).strip()
        return "" if value in ("", "-", "None") else value

    def _v14_obj_label(obj, fallback=""):
        if not obj:
            return fallback
        codigo = _v14_clean(getattr(obj, "codigo", ""))
        nombre = (
            _v14_clean(getattr(obj, "nombre", "")) or
            _v14_clean(getattr(obj, "descripcion", "")) or
            _v14_clean(str(obj))
        )
        if codigo and nombre and codigo not in nombre:
            return f"{codigo} · {nombre}"
        return nombre or codigo or fallback

    filtros_linea_superior_v14_parts = []
    filtros_linea_superior_v14_parts.append(
        f"Periodo: {fecha_desde.strftime('%d/%m/%Y')} — {fecha_hasta.strftime('%d/%m/%Y')}"
    )

    if obra_id.isdigit():
        try:
            _obra_v14 = ObraPlanificacion.objects.filter(pk=int(obra_id)).first()
            filtros_linea_superior_v14_parts.append(f"Obra: {_v14_obj_label(_obra_v14, obra_id)}")
        except Exception:
            filtros_linea_superior_v14_parts.append(f"Obra: {obra_id}")

    if edificio:
        filtros_linea_superior_v14_parts.append(f"Edificio/Fase: {edificio}")

    if vivienda:
        try:
            filtros_linea_superior_v14_parts.append(f"Vivienda: {vivienda_label(vivienda)}")
        except Exception:
            filtros_linea_superior_v14_parts.append(f"Vivienda: {vivienda}")

    if planta:
        filtros_linea_superior_v14_parts.append(f"Planta: {planta}")

    if capitulo_id.isdigit():
        try:
            _cap_v14 = CapituloCatalogo.objects.filter(pk=int(capitulo_id)).first()
            filtros_linea_superior_v14_parts.append(f"Capítulo: {_v14_obj_label(_cap_v14, capitulo_id)}")
        except Exception:
            filtros_linea_superior_v14_parts.append(f"Capítulo: {capitulo_id}")

    if partida_id.isdigit():
        try:
            _part_v14 = PartidaCatalogo.objects.filter(pk=int(partida_id)).first()
            filtros_linea_superior_v14_parts.append(f"Partida: {_v14_obj_label(_part_v14, partida_id)}")
        except Exception:
            filtros_linea_superior_v14_parts.append(f"Partida: {partida_id}")

    if empleado_id.isdigit():
        filtros_linea_superior_v14_parts.append(f"Empleado: {empleado_id}")

    if estado:
        filtros_linea_superior_v14_parts.append(f"Estado: {estado}")

    filtros_linea_superior_v14 = " · ".join(filtros_linea_superior_v14_parts)



    # FIX_ASIGNACIONES_INFORME_HEADER_IMPORTE_V16
    # Total económico visible en KPIs del informe.
    total_importe_v16 = 0.0
    for _row in rows:
        try:
            if isinstance(_row, dict):
                total_importe_v16 += float(_row.get("coste") or 0)
            else:
                total_importe_v16 += float(getattr(_row, "coste", 0) or 0)
        except Exception:
            pass

    total_importe_display_v16 = f"{total_importe_v16:.2f}".replace(".", ",") + " €"


    return render(request, "planificacion_obra/asignaciones_informe.html", {
        "total_importe_display": total_importe_display_v16,
        "filtros_linea_superior_v14": filtros_linea_superior_v14,
        "applied_filters_pairs_v13": applied_filters_pairs_v13,
        "applied_filters_pairs_v12": applied_filters_pairs_v12,
        "filtro_resumen": filtro_resumen,

        "rows": rows,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "total_asignaciones": len(rows),
        "total_empleados": len(empleados_set),
        "total_viviendas": len(viviendas_set),
        "total_horas": round(total_horas, 2),
        "obras": obras,
        "edificios": edificios,
        "viviendas": viviendas,
        "plantas": plantas,
        "capitulos": capitulos,
        "partidas": partidas,
        "empleados": empleados,
        "estados": estados,
        "querystring": querystring,
        "filters": {
            "obra": obra_id,
            "edificio": edificio,
            "vivienda": vivienda,
            "planta": planta,
            "capitulo": capitulo_id,
            "partida": partida_id,
            "empleado": empleado_id,
            "estado": estado,
        },
    })


# ==========================================================
# PLANNING DE OBRA
# ==========================================================


# PLANNING_PLANTAS_CATALOGO_V1
def _planning_merge_planta_names_v1(
    catalog_names,
    legacy_names,
):
    """
    Une plantas configuradas en UnidadObraPlanta con plantas
    históricas existentes en TareaObra.

    Prioridad:
    1. catálogo activo, respetando su orden;
    2. valores legacy que todavía no estén catalogados.

    La deduplicación es case-insensitive.
    """

    result = []
    seen = set()

    for raw in list(catalog_names or []):
        value = str(raw or "").strip()

        if not value:
            continue

        key = value.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(value)


    legacy_clean = sorted(
        {
            str(raw or "").strip()
            for raw in (legacy_names or [])
            if str(raw or "").strip()
        },
        key=lambda value: value.casefold(),
    )


    for value in legacy_clean:
        key = value.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(value)


    return result



from django.contrib.auth.decorators import login_required as _planning_login_required


@_planning_login_required
def planning_list(request):
    from collections import OrderedDict
    from decimal import Decimal
    from django.apps import apps
    from django.db.models import Q
    from django.shortcuts import render
    from planificacion_obra.services_planning import build_tarea_planning_snapshot

    ObraPlanificacion = apps.get_model("planificacion_obra", "ObraPlanificacion")
    FaseObra = apps.get_model("planificacion_obra", "FaseObra")
    TareaObra = apps.get_model("planificacion_obra", "TareaObra")
    UnidadObra = apps.get_model("planificacion_obra", "UnidadObra")
    UnidadObraPlanta = apps.get_model(
        "planificacion_obra",
        "UnidadObraPlanta",
    )
    CapituloCatalogo = apps.get_model("planificacion_obra", "CapituloCatalogo")
    PartidaCatalogo = apps.get_model("planificacion_obra", "PartidaCatalogo")
    TareaRecursoReal = apps.get_model("planificacion_obra", "TareaRecursoReal")

    def by_team(qs):
        if not request.user.is_superuser and hasattr(request.user, "teams"):
            return qs.filter(team__in=request.user.teams.all())
        return qs

    obras = (
        by_team(ObraPlanificacion.objects.select_related("team").all())
        .order_by("team__name", "legacy_cod_obra", "nombre")
    )

    obra_id = request.GET.get("obra") or ""
    fase = request.GET.get("fase") or ""
    vivienda = (request.GET.get("vivienda") or "").strip()
    planta = (request.GET.get("planta") or "").strip()
    capitulo_id = request.GET.get("capitulo") or ""
    partida_id = request.GET.get("partida") or ""
    solo_avisos = request.GET.get("avisos") == "1"
    agrupacion = request.GET.get("agrupacion") or "detalle"
    vista_gantt = request.GET.get("vista") == "gantt"

    agrupaciones_validas = {"detalle", "fase", "vivienda", "capitulo"}
    if agrupacion not in agrupaciones_validas:
        agrupacion = "detalle"

    raw_limit = (request.GET.get("limit") or "200").strip().lower()
    limit_all_requested = raw_limit == "all"
    has_operational_filter = any([fase, vivienda, planta, capitulo_id, partida_id])
    planning_limit_warning = ""

    if limit_all_requested and obra_id and not has_operational_filter:
        limit_all = False
        limit = 500
        limit_value = "500"
        planning_limit_warning = (
            "La opción Todas requiere filtrar por Edificio/Fase, Vivienda, Planta, "
            "Capítulo o Partida. Para proteger el rendimiento se muestran 500 tareas."
        )
    elif limit_all_requested:
        limit_all = True
        limit = None
        limit_value = "all"
    else:
        limit_all = False
        try:
            limit = int(raw_limit)
        except ValueError:
            limit = 200
        limit = max(25, min(limit, 500))
        limit_value = str(limit)

    selected_obra = None
    fases = FaseObra.objects.none()
    capitulos = CapituloCatalogo.objects.none()
    partidas = PartidaCatalogo.objects.none()
    viviendas = []
    plantas = []

    qs = TareaObra.objects.none()

    if obra_id:
        selected_obra = obras.filter(pk=obra_id).first()

    if selected_obra:
        qs = (
            by_team(
                TareaObra.objects.select_related(
                    "team",
                    "obra",
                    "unidad_obra",
                    "capitulo",
                    "partida",
                )
            )
            .filter(obra=selected_obra)
        )

        fases = (
            by_team(FaseObra.objects.filter(obra=selected_obra))
            .order_by("legacy_cod_fase", "nombre")
        )

        # Base para opciones técnicas, respetando estructura si ya está filtrada.
        tecnico_qs = by_team(TareaObra.objects.filter(obra=selected_obra))

        if fase:
            tecnico_qs = tecnico_qs.filter(legacy_cod_fase=fase)

        if vivienda:
            tecnico_qs = tecnico_qs.filter(
                Q(legacy_cod_vivienda=vivienda)
                | Q(unidad_obra__vivienda=vivienda)
            )

        if planta:
            tecnico_qs = tecnico_qs.filter(legacy_planta=planta)

        capitulos = (
            by_team(CapituloCatalogo.objects.filter(tareas__in=tecnico_qs))
            .distinct()
            .order_by("codigo", "nombre")
        )

        partidas_base = tecnico_qs
        if capitulo_id:
            partidas_base = partidas_base.filter(capitulo_id=capitulo_id)

        partidas = (
            by_team(PartidaCatalogo.objects.filter(tareas__in=partidas_base))
            .distinct()
            .order_by("codigo", "nombre")
        )

        # Seguridad backend:
        # si llega una partida que ya no pertenece al capítulo/filtros actuales,
        # se limpia para evitar combinaciones inválidas.
        if partida_id and not partidas.filter(pk=partida_id).exists():
            partida_id = ""

        # Opciones dependientes de estructura:
        # Obra -> Edificio/Fase -> Vivienda -> Planta de trabajo/tarea.
        estructura_qs = by_team(
            TareaObra.objects.filter(obra=selected_obra)
        )

        # PLANNING_VIVIENDAS_SIN_TAREAS_V1_2
        # Las viviendas pertenecen a UnidadObra y deben aparecer
        # aunque aún no tengan tareas de planificación.
        unidades_estructura_qs = by_team(
            UnidadObra.objects.filter(obra=selected_obra)
        )

        if fase:
            unidades_viviendas_qs = (
                unidades_estructura_qs.filter(
                    legacy_cod_fase=fase,
                )
            )

            viviendas_set = set()

            for legacy_vivienda, vivienda_unidad in (
                unidades_viviendas_qs
                .values_list(
                    "legacy_cod_vivienda",
                    "vivienda",
                )
                .order_by(
                    "legacy_cod_vivienda",
                    "vivienda",
                    "id",
                )
            ):
                codigo_vivienda = str(
                    legacy_vivienda
                    or vivienda_unidad
                    or ""
                ).strip()

                if codigo_vivienda:
                    viviendas_set.add(codigo_vivienda)

            viviendas = sorted(viviendas_set)

        # PLANNING_PLANTAS_CATALOGO_V1
        #
        # Planta es una dimensión funcional configurada por UnidadObra.
        #
        # Hasta V1, este selector se construía únicamente desde
        # TareaObra.legacy_planta. Eso hacía imposible seleccionar
        # una planta recién configurada mientras todavía tuviera
        # cero tareas.
        #
        # Contrato:
        #
        #   opciones =
        #       UnidadObraPlanta activas
        #       +
        #       legacy_planta históricos de TareaObra
        #
        # El catálogo gobierna las opciones nuevas.
        # Los valores legacy se conservan para no ocultar históricos.

        plantas_qs = estructura_qs

        if fase:
            plantas_qs = plantas_qs.filter(
                legacy_cod_fase=fase
            )

        if vivienda:
            plantas_qs = plantas_qs.filter(
                Q(legacy_cod_vivienda=vivienda)
                | Q(unidad_obra__vivienda=vivienda)
            )


        legacy_plantas = list(
            plantas_qs
            .exclude(
                legacy_planta__isnull=True
            )
            .exclude(
                legacy_planta=""
            )
            .values_list(
                "legacy_planta",
                flat=True,
            )
            .distinct()
            .order_by(
                "legacy_planta"
            )
        )


        unidades_plantas_qs = (
            unidades_estructura_qs
        )

        if fase:
            unidades_plantas_qs = (
                unidades_plantas_qs.filter(
                    legacy_cod_fase=fase,
                )
            )

        if vivienda:
            unidades_plantas_qs = (
                unidades_plantas_qs.filter(
                    Q(
                        legacy_cod_vivienda=vivienda
                    )
                    | Q(
                        vivienda=vivienda
                    )
                )
            )


        catalog_plantas = list(
            by_team(
                UnidadObraPlanta.objects
                .filter(
                    unidad_obra__in=(
                        unidades_plantas_qs
                    ),
                    activa=True,
                )
            )
            .order_by(
                "orden",
                "nombre",
                "id",
            )
            .values_list(
                "nombre",
                flat=True,
            )
        )


        plantas = (
            _planning_merge_planta_names_v1(
                catalog_plantas,
                legacy_plantas,
            )
        )

        if fase:
            qs = qs.filter(legacy_cod_fase=fase)

        if vivienda:
            qs = qs.filter(
                Q(legacy_cod_vivienda=vivienda)
                | Q(unidad_obra__vivienda=vivienda)
            )

        if planta:
            qs = qs.filter(legacy_planta=planta)

        if capitulo_id:
            qs = qs.filter(capitulo_id=capitulo_id)

        if partida_id:
            qs = qs.filter(partida_id=partida_id)

    qs = qs.order_by(
        "legacy_cod_fase",
        "legacy_cod_vivienda",
        "legacy_planta",
        "legacy_orden",
        "legacy_capitulo",
        "legacy_partida",
    )

    total_filtrado = qs.count()

    if limit_all:
        tareas = list(qs)
    else:
        tareas = list(qs[:limit])

    def _compute_real_dates_for_tareas(tarea_ids):
        """
        Recalcula fechas reales desde TareaRecursoReal:
        - inicio_real = MIN(inicio_recurso_real)
        - fin_real = MAX(fin_recurso_real o inicio_recurso_real)
        """
        result = {}

        if not tarea_ids:
            return result

        recursos = by_team(
            TareaRecursoReal.objects.filter(
                tarea_obra_id__in=tarea_ids,
                inicio_recurso_real__isnull=False,
            )
        ).values("tarea_obra_id", "inicio_recurso_real", "fin_recurso_real")

        for row in recursos:
            tarea_id = row["tarea_obra_id"]
            inicio = row["inicio_recurso_real"]
            fin = row["fin_recurso_real"] or inicio

            current = result.setdefault(tarea_id, {
                "inicio_real": inicio,
                "fin_real": fin,
            })

            if inicio and (current["inicio_real"] is None or inicio < current["inicio_real"]):
                current["inicio_real"] = inicio

            if fin and (current["fin_real"] is None or fin > current["fin_real"]):
                current["fin_real"] = fin

        return result

    fechas_reales_por_tarea = _compute_real_dates_for_tareas([t.id for t in tareas])

    rows = []
    row_items = []

    for tarea in tareas:
        snapshot = build_tarea_planning_snapshot(tarea)

        # Campos operativos para Planning tipo informe.
        # Se añaden aquí para no tocar el servicio de cálculo.
        snapshot.legacy_orden = tarea.legacy_orden
        snapshot.inicio_tarea = tarea.inicio_tarea
        snapshot.fin_tarea = tarea.fin_tarea

        fechas_reales = fechas_reales_por_tarea.get(tarea.id, {})
        snapshot.inicio_real = fechas_reales.get("inicio_real") or tarea.inicio_real
        snapshot.fin_real = fechas_reales.get("fin_real") or tarea.fin_real or snapshot.inicio_real

        if tarea.capitulo:
            snapshot.capitulo_label = f"{tarea.capitulo.codigo} - {tarea.capitulo.nombre}"
        else:
            snapshot.capitulo_label = tarea.legacy_capitulo or "—"

        if tarea.partida:
            snapshot.partida_label = f"{tarea.partida.codigo} - {tarea.partida.nombre}"
        else:
            snapshot.partida_label = tarea.legacy_partida or "—"

        if solo_avisos and not snapshot.warnings:
            continue

        rows.append(snapshot)
        row_items.append((tarea, snapshot))

    def dec(value):
        return value if value is not None else Decimal("0")

    grupos_map = OrderedDict()

    if agrupacion != "detalle":
        for tarea, snapshot in row_items:
            if agrupacion == "fase":
                key = str(tarea.legacy_cod_fase or "-")
                edificio = ""
                if getattr(tarea, "unidad_obra_id", None) and tarea.unidad_obra:
                    edificio = tarea.unidad_obra.edificio or ""
                label = f"{key} · {edificio}" if edificio else key
                tipo = "Edificio/Fase"

            elif agrupacion == "vivienda":
                key = str(snapshot.vivienda or "-")
                label = key
                tipo = "Vivienda"

            elif agrupacion == "capitulo":
                key = str(snapshot.capitulo or "-")
                label = getattr(snapshot, "capitulo_label", None) or key
                tipo = "Capítulo"

            else:
                continue

            if key not in grupos_map:
                grupos_map[key] = {
                    "tipo": tipo,
                    "clave": key,
                    "label": label,
                    "tareas": 0,
                    "coste_previsto": Decimal("0"),
                    "coste_real": Decimal("0"),
                    "horas_previstas": Decimal("0"),
                    "horas_reales": Decimal("0"),
                    "avisos": 0,
                    "rows": [],
                }

            grupo = grupos_map[key]
            grupo["tareas"] += 1
            grupo["coste_previsto"] += dec(snapshot.coste_previsto)
            grupo["coste_real"] += dec(snapshot.coste_real)
            grupo["horas_previstas"] += dec(snapshot.horas_mo_previstas)
            grupo["horas_reales"] += dec(snapshot.horas_mo_reales)
            grupo["avisos"] += len(snapshot.warnings or [])
            grupo["rows"].append(snapshot)

        for grupo in grupos_map.values():
            grupo["desviacion"] = grupo["coste_real"] - grupo["coste_previsto"]
            grupo["ejecucion_pct"] = _pct(grupo["coste_real"], grupo["coste_previsto"])

    grupos = list(grupos_map.values())


    # PLANIFICACION_RESUMEN_VIVIENDAS_PANEL_FASE1B2
    from datetime import date as _date

    vista_resumen_viviendas = bool(selected_obra and not vivienda)
    resumen_viviendas = []
    resumen_viviendas_kpis = {
        "total": 0,
        "activas": 0,
        "retrasadas": 0,
        "completadas": 0,
        "planificadas": 0,
        "sin_fecha": 0,
    }

    if vista_resumen_viviendas:
        _today = _date.today()
        _viviendas_map = OrderedDict()

        # PLANNING_VIVIENDAS_SIN_TAREAS_V1_2
        # Inicializar el pantallazo desde UnidadObra.
        _incluir_unidades_sin_tareas = not any([
            planta,
            capitulo_id,
            partida_id,
            solo_avisos,
        ])

        if _incluir_unidades_sin_tareas:
            _unidades_resumen_qs = by_team(
                UnidadObra.objects.filter(
                    obra=selected_obra,
                )
            )

            if fase:
                _unidades_resumen_qs = (
                    _unidades_resumen_qs.filter(
                        legacy_cod_fase=fase,
                    )
                )

            for unidad_item in (
                _unidades_resumen_qs
                .order_by(
                    "legacy_cod_fase",
                    "legacy_cod_vivienda",
                    "vivienda",
                    "id",
                )
            ):
                _viv_unidad = str(
                    unidad_item.legacy_cod_vivienda
                    or unidad_item.vivienda
                    or ""
                ).strip()

                if not _viv_unidad:
                    continue

                _fase_unidad = unidad_item.legacy_cod_fase
                _key_unidad = (
                    f"{_fase_unidad}::{_viv_unidad}"
                )

                if _key_unidad in _viviendas_map:
                    continue

                _viviendas_map[_key_unidad] = {
                    "obra_id": obra_id,
                    "fase": _fase_unidad,
                    "vivienda": _viv_unidad,
                    "plantas": set(),
                    "total_tareas": 0,
                    "realizadas": 0,
                    "parciales": 0,
                    "pendientes": 0,
                    "retrasadas": 0,
                    "sin_fecha": 0,
                    "pct_sum": Decimal("0"),
                    "inicio_previsto": None,
                    "fin_previsto": None,
                    "inicio_real": None,
                    "fin_real": None,
                    "next_start": None,
                    "trabajando_ahora": False,
                }

        _resumen_qs = qs.values(
            "obra_id",
            "legacy_cod_fase",
            "legacy_cod_vivienda",
            "legacy_planta",
            "inicio_tarea",
            "fin_tarea",
            "inicio_real",
            "fin_real",
            "porcentaje_completado",
        )

        for t in _resumen_qs:
            _viv = (t.get("legacy_cod_vivienda") or "").strip() or "SIN VIVIENDA"
            _fase = t.get("legacy_cod_fase")
            _planta = (t.get("legacy_planta") or "").strip()

            key = f"{_fase}::{_viv}"

            if key not in _viviendas_map:
                _viviendas_map[key] = {
                    "obra_id": obra_id,
                    "fase": _fase,
                    "vivienda": _viv,
                    "plantas": set(),
                    "total_tareas": 0,
                    "realizadas": 0,
                    "parciales": 0,
                    "pendientes": 0,
                    "retrasadas": 0,
                    "sin_fecha": 0,
                    "pct_sum": Decimal("0"),
                    "inicio_previsto": None,
                    "fin_previsto": None,
                    "inicio_real": None,
                    "fin_real": None,
                    "next_start": None,
                    "trabajando_ahora": False,
                }

            item = _viviendas_map[key]

            if _planta:
                item["plantas"].add(_planta)

            item["total_tareas"] += 1

            inicio_prev = t.get("inicio_tarea")
            fin_prev = t.get("fin_tarea")
            inicio_real = t.get("inicio_real")
            fin_real = t.get("fin_real")

            pct = t.get("porcentaje_completado")
            try:
                pct_num = Decimal(str(pct or 0))
            except Exception:
                pct_num = Decimal("0")

            item["pct_sum"] += pct_num

            if inicio_prev and (item["inicio_previsto"] is None or inicio_prev < item["inicio_previsto"]):
                item["inicio_previsto"] = inicio_prev
            if fin_prev and (item["fin_previsto"] is None or fin_prev > item["fin_previsto"]):
                item["fin_previsto"] = fin_prev
            if inicio_real and (item["inicio_real"] is None or inicio_real < item["inicio_real"]):
                item["inicio_real"] = inicio_real
            if fin_real and (item["fin_real"] is None or fin_real > item["fin_real"]):
                item["fin_real"] = fin_real

            if inicio_prev and inicio_prev > _today:
                if item["next_start"] is None or inicio_prev < item["next_start"]:
                    item["next_start"] = inicio_prev

            if not inicio_prev and not fin_prev and not inicio_real and not fin_real:
                item["sin_fecha"] += 1
            elif fin_real or pct_num >= 100:
                item["realizadas"] += 1
            elif fin_prev and fin_prev < _today:
                item["retrasadas"] += 1
            elif inicio_real or pct_num > 0:
                item["parciales"] += 1
                item["trabajando_ahora"] = True
            else:
                item["pendientes"] += 1

        _items = list(_viviendas_map.values())

        for item in _items:
            total = item["total_tareas"] or 1
            item["avance_pct"] = (item["pct_sum"] / Decimal(total)).quantize(Decimal("0.01"))
            item["plantas_label"] = ", ".join(sorted(item["plantas"])) if item["plantas"] else "—"

            if item["total_tareas"] == 0:
                item["estado_label"] = "Sin tareas"
                item["estado_class"] = "bg-secondary"
            elif item["trabajando_ahora"]:
                item["estado_label"] = "En curso"
                item["estado_class"] = "bg-warning text-dark"
            elif item["retrasadas"] > 0:
                item["estado_label"] = "Retrasada"
                item["estado_class"] = "bg-danger"
            elif item["realizadas"] == item["total_tareas"] and item["total_tareas"] > 0:
                item["estado_label"] = "Completada"
                item["estado_class"] = "bg-success"
            elif item["next_start"]:
                item["estado_label"] = "Planificada"
                item["estado_class"] = "bg-primary"
            else:
                item["estado_label"] = "Sin fecha"
                item["estado_class"] = "bg-secondary"

            resumen_viviendas.append(item)

        resumen_viviendas.sort(
            key=lambda x: (
                0 if x["trabajando_ahora"] else
                1 if x["retrasadas"] > 0 else
                2 if x["estado_label"] == "Planificada" else
                3 if x["estado_label"] == "Completada" else
                4,
                x["fase"] or 0,
                x["vivienda"],
            )
        )

        resumen_viviendas_kpis["total"] = len(resumen_viviendas)
        resumen_viviendas_kpis["activas"] = sum(1 for x in resumen_viviendas if x["trabajando_ahora"])
        resumen_viviendas_kpis["retrasadas"] = sum(1 for x in resumen_viviendas if x["retrasadas"] > 0)
        resumen_viviendas_kpis["completadas"] = sum(1 for x in resumen_viviendas if x["estado_label"] == "Completada")
        resumen_viviendas_kpis["planificadas"] = sum(1 for x in resumen_viviendas if x["estado_label"] == "Planificada")
        resumen_viviendas_kpis["sin_fecha"] = sum(
            1
            for x in resumen_viviendas
            if x["estado_label"] in {
                "Sin fecha",
                "Sin tareas",
            }
        )

    vista_vivienda = bool(selected_obra and vivienda)
    resumen_vivienda = None
    if vista_vivienda:
        _prev_total = sum((dec(r.coste_previsto) for r in rows), Decimal("0"))
        _real_total = sum((dec(r.coste_real) for r in rows), Decimal("0"))
        _con_real = sum(1 for r in rows if getattr(r, "inicio_real", None) or getattr(r, "n_reales", 0))
        _avance = None
        if rows:
            _avance = ((Decimal(_con_real) / Decimal(len(rows))) * Decimal("100")).quantize(Decimal("0.01"))
        resumen_vivienda = {
            "inicio_previsto": min([r.inicio_tarea for r in rows if getattr(r, "inicio_tarea", None)], default=None),
            "fin_previsto": max([r.fin_tarea for r in rows if getattr(r, "fin_tarea", None)], default=None),
            "inicio_real": min([r.inicio_real for r in rows if getattr(r, "inicio_real", None)], default=None),
            "fin_real": max([r.fin_real for r in rows if getattr(r, "fin_real", None)], default=None),
            "importe_previsto": _prev_total,
            "importe_real": _real_total,
            "desvio": _real_total - _prev_total,
            "avance_tareas_pct": _avance,
            "avance_coste_pct": _pct(_real_total, _prev_total),
            "total_tareas": len(rows),
            "tareas_con_real": _con_real,
            "tareas_con_avisos": sum(1 for r in rows if getattr(r, "warnings", None)),
        }

    gantt_inicio = None
    gantt_fin = None
    gantt_rows = []
    if vista_vivienda:
        _gantt_dates = []
        for r in rows:
            for _attr in ("inicio_tarea", "fin_tarea", "inicio_real", "fin_real"):
                _value = getattr(r, _attr, None)
                if _value:
                    _gantt_dates.append(_value)

        if _gantt_dates:
            _gantt_start = min(_gantt_dates)
            _gantt_end = max(_gantt_dates)
            gantt_inicio = _gantt_start
            gantt_fin = _gantt_end
            _gantt_total_days = max((_gantt_end - _gantt_start).days + 1, 1)

            def _gantt_bar(_inicio, _fin):
                if not _inicio:
                    return None
                _fin = _fin or _inicio
                if _fin < _inicio:
                    _fin = _inicio

                _left = ((_inicio - _gantt_start).days / _gantt_total_days) * 100
                _width = (((_fin - _inicio).days + 1) / _gantt_total_days) * 100
                _width = max(_width, 1.2)

                if _left + _width > 100:
                    _width = max(1.2, 100 - _left)

                return {"left": f"{_left:.3f}", "width": f"{_width:.3f}"}

            # PLANIFICACION_GANTT_ESTADO_TAREA_FASE1B
            def _gantt_estado_tarea(r):
                today = __import__("datetime").date.today()

                inicio_prev = getattr(r, "inicio_tarea", None)
                fin_prev = getattr(r, "fin_tarea", None)
                inicio_real = getattr(r, "inicio_real", None)
                fin_real = getattr(r, "fin_real", None)
                n_reales = getattr(r, "n_reales", 0) or 0
                pct = getattr(r, "porcentaje_completado", None)

                try:
                    pct_num = float(pct or 0)
                except Exception:
                    pct_num = 0

                if not inicio_prev and not fin_prev and not inicio_real and not fin_real:
                    return {"code": "sin-fecha", "label": "Sin fecha", "class": "bg-secondary"}

                if fin_real or pct_num >= 100:
                    return {"code": "realizada", "label": "Realizada", "class": "bg-success"}

                if fin_prev and fin_prev < today:
                    return {"code": "retrasada", "label": "Retrasada", "class": "bg-danger"}

                if inicio_real or n_reales > 0 or pct_num > 0:
                    return {"code": "parcial", "label": "Parcial", "class": "bg-warning text-dark"}

                return {"code": "pendiente", "label": "Pendiente", "class": "bg-primary"}

            for r in rows:
                _estado_gantt = _gantt_estado_tarea(r)
                gantt_rows.append({
                    "tarea_id": r.tarea_id,
                    "orden": getattr(r, "legacy_orden", None),
                    "partida_label": getattr(r, "partida_label", None) or getattr(r, "partida", ""),
                    "inicio_tarea": getattr(r, "inicio_tarea", None),
                    "fin_tarea": getattr(r, "fin_tarea", None),
                    "inicio_real": getattr(r, "inicio_real", None),
                    "fin_real": getattr(r, "fin_real", None),
                    "prev_bar": _gantt_bar(getattr(r, "inicio_tarea", None), getattr(r, "fin_tarea", None)),
                    "real_bar": _gantt_bar(getattr(r, "inicio_real", None), getattr(r, "fin_real", None)),
                    "estado_code": _estado_gantt["code"],
                    "estado_label": _estado_gantt["label"],
                    "estado_class": _estado_gantt["class"],
                    "late": bool(
                        getattr(r, "fin_real", None)
                        and getattr(r, "fin_tarea", None)
                        and r.fin_real > r.fin_tarea
                    ),
                    "warnings_count": len(getattr(r, "warnings", None) or []),
                })

    # PLANIFICACION_GANTT_CAPITULO_CONTEXT_SAFE_FASE1B4
    if vista_vivienda and vista_gantt and agrupacion == "capitulo" and gantt_rows:
        _cap_map = OrderedDict()

        def _cap_set_min(g, key, value):
            if value and (g[key] is None or value < g[key]):
                g[key] = value

        def _cap_set_max(g, key, value):
            if value and (g[key] is None or value > g[key]):
                g[key] = value

        def _cap_bar(inicio, fin):
            if not gantt_inicio or not gantt_fin:
                return None
            if not inicio and not fin:
                return None
            if inicio and not fin:
                fin = inicio
            if fin and not inicio:
                inicio = fin

            total_days = max((gantt_fin - gantt_inicio).days + 1, 1)
            left = ((inicio - gantt_inicio).days / total_days) * 100
            width = (((fin - inicio).days + 1) / total_days) * 100

            return {
                "left": max(0, min(100, round(left, 2))),
                "width": max(0.7, min(100, round(width, 2))),
            }

        def _estado_snapshot(snapshot):
            inicio_prev = getattr(snapshot, "inicio_tarea", None)
            fin_prev = getattr(snapshot, "fin_tarea", None)
            inicio_real = getattr(snapshot, "inicio_real", None)
            fin_real = getattr(snapshot, "fin_real", None)
            n_reales = getattr(snapshot, "n_reales", 0) or 0
            pct = getattr(snapshot, "porcentaje_completado", None)

            try:
                pct_num = float(pct or 0)
            except Exception:
                pct_num = 0

            if not inicio_prev and not fin_prev and not inicio_real and not fin_real:
                return "sin-fecha"
            if fin_real or pct_num >= 100:
                return "realizada"
            if fin_prev and fin_prev < __import__("datetime").date.today():
                return "retrasada"
            if inicio_real or n_reales > 0 or pct_num > 0:
                return "parcial"
            return "pendiente"

        for snapshot in rows:
            label = (
                getattr(snapshot, "capitulo_label", None)
                or getattr(snapshot, "capitulo", None)
                or "—"
            )

            if label not in _cap_map:
                _cap_map[label] = {
                    "label": label,
                    "orden": len(_cap_map) + 1,
                    "total": 0,
                    "realizadas": 0,
                    "parciales": 0,
                    "pendientes": 0,
                    "retrasadas": 0,
                    "sin_fecha": 0,
                    "warnings_count": 0,
                    "inicio_tarea": None,
                    "fin_tarea": None,
                    "inicio_real": None,
                    "fin_real": None,
                    # PLANIFICACION_GANTT_CAPITULO_SEGMENTOS_V2
                    "prev_segments": [],
                    "real_segments": [],
                }

            g = _cap_map[label]
            g["total"] += 1
            g["warnings_count"] += len(getattr(snapshot, "warnings", None) or [])

            code = _estado_snapshot(snapshot)
            if code == "realizada":
                g["realizadas"] += 1
            elif code == "parcial":
                g["parciales"] += 1
            elif code == "retrasada":
                g["retrasadas"] += 1
            elif code == "sin-fecha":
                g["sin_fecha"] += 1
            else:
                g["pendientes"] += 1

            inicio_prev = getattr(snapshot, "inicio_tarea", None)
            fin_prev = getattr(snapshot, "fin_tarea", None) or inicio_prev
            inicio_real = getattr(snapshot, "inicio_real", None)
            fin_real = getattr(snapshot, "fin_real", None) or inicio_real

            _cap_set_min(g, "inicio_tarea", inicio_prev)
            _cap_set_max(g, "fin_tarea", fin_prev)
            _cap_set_min(g, "inicio_real", inicio_real)
            _cap_set_max(g, "fin_real", fin_real)

            _prev_segment = _cap_bar(inicio_prev, fin_prev)
            if _prev_segment:
                g["prev_segments"].append(_prev_segment)

            _real_segment = _cap_bar(inicio_real, fin_real)
            if _real_segment:
                _real_segment["late"] = bool(fin_real and fin_prev and fin_real > fin_prev)
                g["real_segments"].append(_real_segment)

        _grouped_rows = []

        for g in _cap_map.values():
            total = g["total"] or 1
            avance = ((Decimal(g["realizadas"]) / Decimal(total)) * Decimal("100")).quantize(Decimal("0.01"))

            if g["sin_fecha"] == g["total"]:
                estado = {"code": "sin-fecha", "label": "Sin fecha", "class": "bg-secondary"}
            elif g["realizadas"] == g["total"]:
                estado = {"code": "realizada", "label": "Realizado", "class": "bg-success"}
            elif g["retrasadas"] > 0:
                estado = {"code": "retrasada", "label": "Retrasado", "class": "bg-danger"}
            elif g["parciales"] > 0:
                estado = {"code": "parcial", "label": "En curso", "class": "bg-warning text-dark"}
            else:
                estado = {"code": "pendiente", "label": "Pendiente", "class": "bg-primary"}

            late = bool(g["fin_real"] and g["fin_tarea"] and g["fin_real"] > g["fin_tarea"])

            _grouped_rows.append({
                "tarea_id": None,
                "orden": g["orden"],
                "partida_label": g["label"],
                "estado_code": estado["code"],
                "estado_label": estado["label"],
                "estado_class": estado["class"],
                "warnings_count": g["warnings_count"],
                "inicio_tarea": g["inicio_tarea"],
                "fin_tarea": g["fin_tarea"],
                "inicio_real": g["inicio_real"],
                "fin_real": g["fin_real"],
                "prev_bar": _cap_bar(g["inicio_tarea"], g["fin_tarea"]),
                "real_bar": _cap_bar(g["inicio_real"], g["fin_real"]),
                "prev_segments": g.get("prev_segments", []),
                "real_segments": g.get("real_segments", []),
                "late": late,
                "meta_label": f'{g["total"]} tareas · {avance}% avance',
            })

        gantt_rows = _grouped_rows

    context = {
        "obras": obras,
        "selected_obra": selected_obra,
        "fases": fases,
        "viviendas": viviendas,
        "plantas": plantas,
        "capitulos": capitulos,
        "partidas": partidas,
        "rows": rows,
        "grupos": grupos,
          "vista_resumen_viviendas": vista_resumen_viviendas,
          "resumen_viviendas": resumen_viviendas,
          "resumen_viviendas_kpis": resumen_viviendas_kpis,
          "vista_vivienda": vista_vivienda,
          "resumen_vivienda": resumen_vivienda,
          "vista_gantt": vista_gantt,
          "gantt_rows": gantt_rows,
          "gantt_inicio": gantt_inicio,
          "gantt_fin": gantt_fin,
        "total_filtrado": total_filtrado,
        "total_mostrado": len(rows),
        "limit": limit_value,
        "planning_limit_warning": planning_limit_warning,
        "solo_avisos": solo_avisos,
        "agrupacion": agrupacion,
              "vista": "gantt" if vista_gantt else "",
        "filtros": {
            "obra": str(obra_id),
            "fase": str(fase),
            "vivienda": vivienda,
            "planta": planta,
            "capitulo": str(capitulo_id),
            "partida": str(partida_id),
            "agrupacion": agrupacion,
              "vista": "gantt" if vista_gantt else "",
        },
    }

    # PLANIFICACION_NAV_SIMPLE_PLANNING_CONTEXT_V1
    context["planning_bajar_nivel_url"] = _po_bajar_nivel_url(request.get_full_path())
    context["planning_sin_filtro_url"] = _po_planning_base_url()
    return render(request, "planificacion_obra/planning_list.html", context)


# OBRA_MATERIALES_ASIGNADOS_TRACEABILITY_REPORT_V1
def _materiales_access_flags(user):
    authenticated = bool(user and user.is_authenticated)
    return {
        "can_view": authenticated and (user.is_superuser or user.has_perm("planificacion_obra.view_tarearecursoreal")),
        "can_view_amounts": authenticated and (user.is_superuser or user.has_perm("gestion.view_facturaproveedorgestion")),
        "can_view_albaran": authenticated and (user.is_superuser or user.has_perm("gestion.view_albaranproveedorgestion")),
        "can_view_factura": authenticated and (user.is_superuser or user.has_perm("gestion.view_facturaproveedorgestion")),
        "can_export": authenticated and (user.is_superuser or user.has_perm("planificacion_obra.view_tarearecursoreal")),
    }


def _materiales_obra_for_request(request):
    from django.http import Http404
    obra_id = (request.GET.get("obra") or "").strip()
    if not obra_id:
        return None
    qs = ObraPlanificacion.objects.select_related("team")
    if not request.user.is_superuser:
        qs = qs.filter(team__in=request.user.teams.all())
    try:
        return qs.get(pk=obra_id)
    except (ObraPlanificacion.DoesNotExist, ValueError):
        raise Http404("Obra no disponible.")


def _materiales_filters(request):
    from django.utils.dateparse import parse_date
    return {
        "desde": parse_date(request.GET.get("desde", "")), "hasta": parse_date(request.GET.get("hasta", "")),
        "proveedor": request.GET.get("proveedor", ""), "recurso": request.GET.get("recurso", ""),
        "documento": request.GET.get("documento", "TODOS"), "fase": request.GET.get("fase", ""),
        "vivienda": request.GET.get("vivienda", ""), "planta": request.GET.get("planta", ""),
        "capitulo": request.GET.get("capitulo", ""), "partida": request.GET.get("partida", ""),
        "valoracion": request.GET.get("valoracion", "TODOS"),
    }


@login_required
def materiales_asignados_report(request):
    from django.core.paginator import Paginator
    from django.http import HttpResponseForbidden
    from planificacion_obra.materiales_asignados import build_materiales_report, materiales_queryset

    flags = _materiales_access_flags(request.user)
    if not flags["can_view"]:
        return HttpResponseForbidden("No tiene permiso para consultar materiales reales.")
    obra = _materiales_obra_for_request(request)
    obras = ObraPlanificacion.objects.select_related("team").all()
    if not request.user.is_superuser:
        obras = obras.filter(team__in=request.user.teams.all())
    filters = _materiales_filters(request)
    report = {"details": [], "summary": [], "totals": {"assignments": 0, "articles": 0, "documents": 0, "base": 0, "iva": 0, "total": 0, "unvalued": 0, "ambiguous": 0}}
    if obra:
        report = build_materiales_report(obra, filters, flags["can_view_amounts"], flags["can_view_albaran"], flags["can_view_factura"])
    page = Paginator(report["details"], 100).get_page(request.GET.get("page", 1))
    base_rows = materiales_queryset(obra) if obra else TareaRecursoReal.objects.none()
    resources = RecursoCatalogo.objects.filter(pk__in=base_rows.values("recurso_id")).order_by("nombre", "pk")
    providers = sorted({x["provider"] for x in report["details"] if x["provider"]}, key=lambda p: str(p).casefold())
    fases_materiales = FaseObra.objects.filter(obra=obra).order_by("legacy_cod_fase") if obra else FaseObra.objects.none()
    viviendas_materiales = UnidadObra.objects.filter(obra=obra).order_by("edificio", "vivienda", "pk") if obra else UnidadObra.objects.none()
    capitulos_materiales = CapituloCatalogo.objects.filter(team=obra.team).order_by("codigo") if obra else CapituloCatalogo.objects.none()
    partidas_materiales = PartidaCatalogo.objects.filter(team=obra.team, tareas__obra=obra).distinct().order_by("capitulo__codigo", "codigo") if obra else PartidaCatalogo.objects.none()
    plantas_materiales = list(base_rows.exclude(legacy_planta="").order_by().values_list("legacy_planta", flat=True).distinct())
    context = {"obra": obra, "obras": obras.order_by("team__name", "legacy_cod_obra"), "report": report, "page_obj": page,
               "filters": filters, "resources": resources, "providers": providers, **flags,
               "fases_materiales": fases_materiales, "viviendas_materiales": viviendas_materiales,
               "capitulos_materiales": capitulos_materiales, "partidas_materiales": partidas_materiales,
               "plantas_materiales": plantas_materiales,
               "print_mode": request.GET.get("print") == "1"}
    return render(request, "planificacion_obra/materiales_asignados.html", context)


@login_required
def materiales_asignados_csv(request):
    import csv
    from django.http import HttpResponse, HttpResponseForbidden
    from planificacion_obra.materiales_asignados import build_materiales_report, csv_safe
    flags = _materiales_access_flags(request.user)
    if not flags["can_view"] or not flags["can_export"]:
        return HttpResponseForbidden("No tiene permiso para exportar materiales reales.")
    obra = _materiales_obra_for_request(request)
    if not obra:
        return HttpResponseForbidden("Debe seleccionar una obra.")
    report = build_materiales_report(obra, _materiales_filters(request), flags["can_view_amounts"], flags["can_view_albaran"], flags["can_view_factura"])
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="materiales-obra-{obra.pk}.csv"'
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    headers = ["Fecha", "Código", "Artículo", "Cantidad", "Unidad"]
    if flags["can_view_amounts"]:
        headers += ["Precio unitario histórico", "Total neto asignado"]
    headers += ["Origen", "Proveedor", "Destino", "Albarán", "Factura", "Asignación canónica", "Advertencia"]
    writer.writerow(headers)
    for x in report["details"]:
        row = [x["date"], x["code"], x["article"], x["quantity"], x["unit"]]
        if flags["can_view_amounts"]:
            row += [x["price"], x["net_total"]]
        row += [x["origin"], str(x["provider"] or ""), x["destination"], x["albaran"].cod_albaran if x["albaran"] else "", x["factura"].cod_factura if x["factura"] else "", x["identity"], x["warning"]]
        writer.writerow([csv_safe(v) for v in row])
    return response


@login_required
def materiales_asignados_print(request):
    from django.http import HttpResponseForbidden
    from django.utils import timezone
    from planificacion_obra.materiales_asignados import build_materiales_report
    flags = _materiales_access_flags(request.user)
    if not flags["can_view"]:
        return HttpResponseForbidden("No tiene permiso para imprimir materiales reales.")
    obra = _materiales_obra_for_request(request)
    if not obra:
        return HttpResponseForbidden("Debe seleccionar una obra.")
    filters = _materiales_filters(request)
    report = build_materiales_report(obra, filters, flags["can_view_amounts"], flags["can_view_albaran"], flags["can_view_factura"])
    return render(request, "planificacion_obra/materiales_asignados_print.html", {
        "obra": obra, "report": report, "rows": report["details"], "filters": filters,
        "generated_at": timezone.localtime(), "generated_by": request.user,
        "can_view_amounts": flags["can_view_amounts"],
    })



@_planning_login_required
# PLANIFICACION_NAV_FILTROS_V2
def _po_planning_base_url_old_disabled(request=None):
    from django.urls import reverse
    return reverse("planificacion_obra:planning_list")


def _po_safe_next_url(value):
    value = (value or "").strip()
    if not value:
        return ""

    # RECURSOS_OBRA_RETURN_CONTEXT_V1_2
    # Solo se admiten destinos internos conocidos de Planificación.
    allowed = (
        "/app/planificacion-obra/planning/",
        "/app/planificacion-obra/viviendas/estado/",
        "/app/planificacion-obra/recursos/",
        "/app/planificacion-obra/asignaciones/",
    )

    if value.startswith(allowed):
        return value

    return ""


def _po_url_with_next(url, next_url):
    from urllib.parse import quote
    safe = _po_safe_next_url(next_url)
    if not safe:
        return url
    return f"{url}?next={quote(safe, safe='')}"


def _po_bajar_nivel_url_old_disabled(next_url=None):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    safe = _po_safe_next_url(next_url)
    if not safe:
        return _po_planning_base_url()

    parts = urlsplit(safe)
    pairs = parse_qsl(parts.query, keep_blank_values=True)

    hierarchy = ["obra", "fase", "vivienda", "planta", "capitulo", "partida"]
    values = {k: v for k, v in pairs if k in hierarchy and v not in ("", None)}

    deepest = None
    for i, key in enumerate(hierarchy):
        if key in values:
            deepest = i

    if deepest is None:
        return _po_planning_base_url()

    remove = set(hierarchy[deepest:])
    new_pairs = [(k, v) for k, v in pairs if k not in remove]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(new_pairs, doseq=True), parts.fragment))


# PLANIFICACION_NAV_BASE_URL_DEFINITIVO_FIX
def _po_planning_base_url(request=None):
    from django.urls import reverse
    return reverse("planificacion_obra:planning_list")


# PLANIFICACION_NAV_SIMPLE_VOLVER_BAJAR_V1
def _po_bajar_nivel_url(next_url):
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    base = _po_planning_base_url()
    safe = _po_safe_next_url(next_url) or (next_url or "")
    if not safe:
        return base

    parts = urlsplit(safe)
    pairs = parse_qsl(parts.query, keep_blank_values=True)

    hierarchy = ["obra", "fase", "vivienda", "planta", "capitulo", "partida"]
    empty_values = {"", "all", "ALL", "todos", "TODOS", "Todas", "todas", "None", "none"}

    values = {}
    for k, v in pairs:
        if k in hierarchy and str(v) not in empty_values:
            values[k] = v

    deepest = None
    for i, key in enumerate(hierarchy):
        if key in values:
            deepest = i

    if deepest is None:
        return base

    # Quitar solo el nivel activo más profundo y cualquier inferior.
    remove = set(hierarchy[deepest:])
    new_pairs = [(k, v) for k, v in pairs if k not in remove]

    query = urlencode(new_pairs, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path or base, query, parts.fragment))


def planning_tarea_detail(request, pk):
    from django.apps import apps
    from django.shortcuts import get_object_or_404, render
    from planificacion_obra.services_planning import build_tarea_planning_snapshot

    TareaObra = apps.get_model("planificacion_obra", "TareaObra")
    TareaRecursoPrevisto = apps.get_model("planificacion_obra", "TareaRecursoPrevisto")
    TareaRecursoReal = apps.get_model("planificacion_obra", "TareaRecursoReal")

    def by_team(qs):
        if not request.user.is_superuser and hasattr(request.user, "teams"):
            return qs.filter(team__in=request.user.teams.all())
        return qs

    tarea = get_object_or_404(
        by_team(
            TareaObra.objects.select_related(
                "team", "obra", "unidad_obra", "capitulo", "partida"
            )
        ),
        pk=pk,
    )

    snapshot = build_tarea_planning_snapshot(tarea)

    recursos_previstos = (
        by_team(
            TareaRecursoPrevisto.objects.select_related(
                "recurso", "unidad_obra", "partida"
            )
        )
        .filter(tarea_obra=tarea)
        .order_by("legacy_orden_recurso", "id")
    )

    recursos_reales = (
        by_team(
            TareaRecursoReal.objects.select_related(
                "recurso", "empleado", "unidad_obra", "partida"
            )
        )
        .filter(tarea_obra=tarea)
        .order_by("inicio_recurso_real", "legacy_orden_recurso", "id")
    )

    inicio_real_recalculado = None
    fin_real_recalculado = None

    for recurso_real in recursos_reales:
        inicio = recurso_real.inicio_recurso_real
        if not inicio:
            continue

        fin = recurso_real.fin_recurso_real or inicio

        if inicio_real_recalculado is None or inicio < inicio_real_recalculado:
            inicio_real_recalculado = inicio

        if fin_real_recalculado is None or fin > fin_real_recalculado:
            fin_real_recalculado = fin

    snapshot.inicio_real = inicio_real_recalculado or tarea.inicio_real
    snapshot.fin_real = fin_real_recalculado or tarea.fin_real or snapshot.inicio_real

    next_url = _po_safe_next_url(request.GET.get("next")) or _po_planning_base_url()

    context = {
        "tarea": tarea,
        "snapshot": snapshot,
        "recursos_previstos": recursos_previstos,
        "recursos_reales": recursos_reales,
        "next_url": next_url,
        "bajar_nivel_url": _po_bajar_nivel_url(next_url),
        "sin_filtro_url": _po_planning_base_url(),
    }

    return render(request, "planificacion_obra/planning_tarea_detail.html", context)

# === TAREA_MANUAL_PORTAL_V1 ===
from uuid import uuid4 as _tm_uuid4
from django.db.models import Max as _tm_Max
from django.urls import reverse as _tm_reverse
from django.utils import timezone as _tm_timezone
from .forms import TareaObraSimpleForm as _TareaObraManualForm


@login_required
def tarea_manual_create(request, obra_pk=None):
    # PLANNING_NEW_TASK_RETURN_CONTEXT_V1
    from django.db import (
        transaction as _tm_transaction,
    )

    next_candidate = (
        request.POST.get("next")
        if request.method == "POST"
        else request.GET.get("next")
    )

    next_url = (
        _po_safe_next_url(
            next_candidate
        )
    )

    obra_locked = None
    if obra_pk is not None:
        obra_locked = get_object_or_404(
            _obras_scope_qs(request).select_related("team"),
            pk=obra_pk,
        )

    elif request.method == "GET":
        raw_obra = str(
            request.GET.get("obra")
            or ""
        ).strip()

        if raw_obra.isdigit():
            obras_scope = (
                _obras_scope_qs(request)
                .select_related("team")
            )

            obra_locked = (
                obras_scope
                .filter(
                    pk=int(raw_obra)
                )
                .first()
            )

            if obra_locked is None:
                obra_locked = (
                    obras_scope
                    .filter(
                        legacy_cod_obra=(
                            int(raw_obra)
                        )
                    )
                    .first()
                )

    if request.method == "POST":
        form = _TareaObraManualForm(request.POST, request=request, obra=obra_locked)
        if form.is_valid():
            tarea = form.save(commit=False)
            obra = tarea.obra

            tarea.team = obra.team
            tarea.legacy_cod_obra = obra.legacy_cod_obra

            if not tarea.legacy_key:
                tarea.legacy_key = f"PORTAL-MANUAL-{obra.pk}-{_tm_uuid4().hex[:12]}"

            unidad = tarea.unidad_obra
            if unidad:
                tarea.legacy_cod_fase = unidad.legacy_cod_fase
                tarea.legacy_cod_vivienda = unidad.legacy_cod_vivienda or unidad.vivienda or ""
                # UNIDAD_OBRA_PLANTAS_VIEW_V1
                # La planta procede del catálogo
                # asociado a la unidad de obra.

            if tarea.capitulo:
                tarea.legacy_capitulo = tarea.capitulo.codigo or ""

            if tarea.partida:
                if not tarea.capitulo:
                    tarea.capitulo = tarea.partida.capitulo
                    tarea.legacy_capitulo = tarea.capitulo.codigo or ""
                tarea.legacy_partida = tarea.partida.codigo or ""
                if not tarea.programacion:
                    tarea.programacion = (tarea.partida.nombre or tarea.partida.codigo or "")[:80]
                if not tarea.tipo_partida:
                    tarea.tipo_partida = tarea.partida.tipo_partida or ""
                if not tarea.unidad:
                    tarea.unidad = tarea.partida.unidad or ""

            if tarea.porcentaje_completado is None:
                tarea.porcentaje_completado = Decimal("0.00")

            if tarea.importe_tarea is None and tarea.cantidad is not None and tarea.precio_unidad is not None:
                tarea.importe_tarea = (tarea.cantidad * tarea.precio_unidad).quantize(Decimal("0.01"))

            raw = (
                dict(tarea.raw_data)
                if isinstance(
                    tarea.raw_data,
                    dict,
                )
                else {}
            )

            raw.update({
                "origen": "portal_manual",
                "creado_desde": "tarea_manual_create",
                "created_by_user_id": getattr(request.user, "id", None),
                "created_at": _tm_timezone.now().isoformat(),
            })

            with _tm_transaction.atomic():
                # PLANNING_TASK_ORDER_SCOPE_V1
                # El orden pertenece a:
                # obra + fase + vivienda + planta.
                # Se bloquea la unidad para serializar
                # dos altas concurrentes.
                if tarea.unidad_obra_id:
                    (
                        tarea.unidad_obra
                        .__class__
                        .objects
                        .select_for_update()
                        .get(
                            pk=tarea.unidad_obra_id
                        )
                    )
                else:
                    (
                        obra.__class__
                        .objects
                        .select_for_update()
                        .get(pk=obra.pk)
                    )

                if tarea.legacy_orden is None:
                    max_orden = (
                        TareaObra.objects
                        .filter(
                            team=tarea.team,
                            obra=obra,
                            legacy_cod_fase=(
                                tarea.legacy_cod_fase
                            ),
                            legacy_cod_vivienda=(
                                tarea
                                .legacy_cod_vivienda
                            ),
                            legacy_planta__iexact=(
                                tarea.legacy_planta
                            ),
                        )
                        .aggregate(
                            max_orden=_tm_Max(
                                "legacy_orden"
                            )
                        )
                        .get("max_orden")
                        or 0
                    )

                    tarea.legacy_orden = (
                        int(max_orden)
                        + 1
                    )

                raw["orden_scope"] = {
                    "team_id": tarea.team_id,
                    "obra_id": tarea.obra_id,
                    "fase": (
                        tarea.legacy_cod_fase
                    ),
                    "vivienda": (
                        tarea
                        .legacy_cod_vivienda
                    ),
                    "planta": (
                        tarea.legacy_planta
                    ),
                }

                tarea.raw_data = raw
                tarea.save()

            messages.success(
                request,
                (
                    "Tarea creada correctamente "
                    f"con orden {tarea.legacy_orden}."
                ),
            )

            if next_url:
                return redirect(next_url)

            return redirect(
                "planificacion_obra:"
                "planning_tarea_detail",
                pk=tarea.pk,
            )
    else:
        # PLANNING_NEW_TASK_CONTEXT_INITIAL_V1
        probe_form = _TareaObraManualForm(
            request=request,
            obra=obra_locked,
        )

        initial = {}

        raw_fase = str(
            request.GET.get("fase")
            or ""
        ).strip()

        raw_vivienda = str(
            request.GET.get("vivienda")
            or ""
        ).strip()

        raw_planta = str(
            request.GET.get("planta")
            or ""
        ).strip()

        raw_capitulo = str(
            request.GET.get("capitulo")
            or ""
        ).strip()

        unidad = None

        if raw_vivienda:
            unidades = (
                probe_form
                .fields["unidad_obra"]
                .queryset
                .filter(
                    legacy_cod_vivienda__iexact=(
                        raw_vivienda
                    )
                )
            )

            if raw_fase.isdigit():
                unidades = (
                    unidades.filter(
                        legacy_cod_fase=(
                            int(raw_fase)
                        )
                    )
                )

            unidad = (
                unidades
                .order_by("pk")
                .first()
            )

        if unidad is not None:
            initial[
                "unidad_obra"
            ] = unidad.pk

        if raw_planta:
            initial[
                "legacy_planta"
            ] = raw_planta

        capitulo = None

        if raw_capitulo:
            capitulos = (
                probe_form
                .fields["capitulo"]
                .queryset
            )

            if raw_capitulo.isdigit():
                capitulo = (
                    capitulos
                    .filter(
                        pk=int(raw_capitulo)
                    )
                    .first()
                )

            if capitulo is None:
                capitulo = (
                    capitulos
                    .filter(
                        codigo__iexact=(
                            raw_capitulo
                        )
                    )
                    .first()
                )

        if capitulo is not None:
            initial[
                "capitulo"
            ] = capitulo.pk

        # La partida es el nuevo elemento
        # que debe escoger el usuario.
        initial["partida"] = None

        form = _TareaObraManualForm(
            request=request,
            obra=obra_locked,
            initial=initial,
        )

    if obra_locked is not None:
        cancel_url = _tm_reverse(
            "planificacion_obra:"
            "obra_tareas_list",
            args=[obra_locked.pk],
        )
    else:
        cancel_url = _tm_reverse(
            "planificacion_obra:"
            "planning_list"
        )

    cancel_url = (
        next_url
        or cancel_url
    )

    return render(
        request,
        "planificacion_obra/tarea_form.html",
        {
            "form": form,
            "obra": obra_locked,
            "cancel_url": cancel_url,
            "next_url": next_url,
            "titulo": (
                "Nueva tarea "
                "de planificación"
            ),
        },
    )

# === TAREA_RECURSOS_MANUALES_V1 ===
from django.db.models import Max as _tr_Max
from django.utils import timezone as _tr_timezone
from datetime import timedelta as _tr_timedelta

# RECURSO_REAL_EMPLEADO_MULTIDIA_V1
def _tr_default_employee_hours(day):
    # Monday=0 ... Sunday=6
    wd = day.weekday()
    if wd in (0, 1, 2, 3):
        return Decimal('9.00')
    if wd == 4:
        return Decimal('6.00')
    return Decimal('0.00')

def _tr_employee_workdays(start, end):
    if not start:
        return []
    end = end or start
    days = []
    current = start
    while current <= end:
        hours = _tr_default_employee_hours(current)
        if hours > 0:
            days.append((current, hours))
        current = current + _tr_timedelta(days=1)
    return days



def _tr_get_tarea_for_user(request, pk):
    qs = TareaObra.objects.select_related("team", "obra", "unidad_obra", "capitulo", "partida")
    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs = qs.filter(team__in=request.user.teams.all())
    return get_object_or_404(qs, pk=pk)


def _tr_fill_common_previsto(obj, tarea):
    obj.team = tarea.team
    obj.tarea_obra = tarea
    obj.unidad_obra = tarea.unidad_obra
    obj.partida = tarea.partida
    obj.legacy_cod_obra = tarea.legacy_cod_obra
    obj.legacy_cod_fase = tarea.legacy_cod_fase
    obj.legacy_cod_vivienda = tarea.legacy_cod_vivienda
    obj.legacy_planta = tarea.legacy_planta
    obj.legacy_cod_partida = tarea.legacy_partida

    max_row = (
        TareaRecursoPrevisto.objects
        .filter(team=tarea.team)
        .aggregate(m=_tr_Max("legacy_row_number"))
        .get("m")
        or 0
    )
    obj.legacy_row_number = int(max_row) + 1

    max_orden = (
        TareaRecursoPrevisto.objects
        .filter(team=tarea.team, tarea_obra=tarea)
        .aggregate(m=_tr_Max("legacy_orden_recurso"))
        .get("m")
        or 0
    )
    obj.legacy_orden_recurso = int(max_orden) + 1

    if obj.recurso:
        obj.legacy_id_recurso = obj.recurso.legacy_id

    raw = obj.raw_data or {}
    raw.update({
        "origen": "portal_manual",
        "creado_desde": "tarea_recurso_previsto_create",
        "created_by_user_id": getattr(tarea, "id", None),
        "created_at": _tr_timezone.now().isoformat(),
    })
    obj.raw_data = raw


def _tr_fill_common_real(obj, tarea):
    obj.team = tarea.team
    obj.tarea_obra = tarea
    obj.unidad_obra = tarea.unidad_obra
    obj.partida = tarea.partida
    obj.legacy_cod_obra = tarea.legacy_cod_obra
    obj.legacy_cod_fase = tarea.legacy_cod_fase
    obj.legacy_cod_vivienda = tarea.legacy_cod_vivienda
    obj.legacy_planta = tarea.legacy_planta
    obj.legacy_capitulo = tarea.legacy_capitulo
    obj.legacy_partida = tarea.legacy_partida

    max_id = (
        TareaRecursoReal.objects
        .filter(team=tarea.team)
        .aggregate(m=_tr_Max("legacy_id_recurso_tarea"))
        .get("m")
        or 0
    )
    obj.legacy_id_recurso_tarea = int(max_id) + 1

    max_orden = (
        TareaRecursoReal.objects
        .filter(team=tarea.team, tarea_obra=tarea)
        .aggregate(m=_tr_Max("legacy_orden_recurso"))
        .get("m")
        or 0
    )
    obj.legacy_orden_recurso = int(max_orden) + 1

    if obj.recurso:
        obj.legacy_id_recurso = obj.recurso.legacy_id
        obj.legacy_tipo_recurso = obj.recurso.tipo or ""
    elif obj.empleado:
        obj.legacy_personal = obj.empleado.legacy_id
        obj.legacy_tipo_recurso = "M.O. ADM."

    obj.costo_recurso = obj.costo_recurso_real

    raw = obj.raw_data or {}
    raw.update({
        "origen": "portal_manual",
        "creado_desde": "tarea_recurso_real_create",
        "created_by_user_id": getattr(tarea, "id", None),
        "created_at": _tr_timezone.now().isoformat(),
    })
    obj.raw_data = raw


@login_required
def tarea_recurso_previsto_create(request, pk):
    from .forms import TareaRecursoPrevistoManualForm

    tarea = _tr_get_tarea_for_user(request, pk)

    # PLANIFICACION_RECURSO_REAL_NO_LABORABLE_CONFIRM_V1
    requiere_confirmar_no_laborable = False
    confirmar_no_laborable = request.POST.get("confirmar_no_laborable") == "1"

    if request.method == "POST":
        form = TareaRecursoPrevistoManualForm(request.POST, tarea=tarea)
        if form.is_valid():
            obj = form.save(commit=False)
            _tr_fill_common_previsto(obj, tarea)
            obj.save()
            messages.success(request, "Recurso previsto añadido correctamente.")
            return redirect("planificacion_obra:planning_tarea_detail", pk=tarea.pk)
    else:
        form = TareaRecursoPrevistoManualForm(tarea=tarea)

    return render(
        request,
        "planificacion_obra/tarea_recurso_form.html",
        {
            "form": form,
            "tarea": tarea,
            "titulo": "Añadir recurso previsto",
            "tipo": "previsto",
            "cancel_url": _tm_reverse("planificacion_obra:planning_tarea_detail", args=[tarea.pk]),
            "requiere_confirmar_no_laborable": requiere_confirmar_no_laborable,
        },
    )


@login_required
def tarea_recurso_real_create(request, pk):
    from .forms import TareaRecursoRealManualForm

    tarea = _tr_get_tarea_for_user(request, pk)

    # PLANIFICACION_RECURSO_REAL_NO_LABORABLE_CONFIRM_DECL_V2
    requiere_confirmar_no_laborable = False
    confirmar_no_laborable = request.POST.get("confirmar_no_laborable") == "1"

    if request.method == "POST":
        form = TareaRecursoRealManualForm(request.POST, tarea=tarea)
        if form.is_valid():
            operation_id = (
                _tm_uuid4().hex
            )

            base = form.save(
                commit=False
            )

            base._portal_tipo_recurso_ui = (
                request.POST.get(
                    "tipo_recurso_ui"
                )
                or ""
            )

            # PLANIFICACION_RECURSO_REAL_CREATE_CANTIDAD_MANDA_MIN_V1
            # Cantidad manda siempre; en mano de obra equivale a horas reales.
            cantidad_manual = base.cantidad if base.cantidad is not None else base.horas_reales
            if cantidad_manual is not None:
                base.cantidad = cantidad_manual
                base.horas_reales = cantidad_manual

            # Mano de obra: si hay empleado, unidad HRS, precio desde EmpleadoObra,
            # y si hay rango de fechas se divide en una línea por día laborable.
            if base.empleado:
                base.unidad = "HRS"

                if base.precio_unidad is None:
                    base.precio_unidad = base.empleado.precio_hora

                start_day = base.inicio_recurso_real
                end_day = base.fin_recurso_real or start_day

                if start_day and end_day and end_day < start_day:
                    form.add_error("fin_recurso_real", "La fecha fin no puede ser anterior a la fecha inicio.")
                else:
                    workdays = _tr_employee_workdays(start_day, end_day) if start_day else []

                    # Si no hay fechas, se crea una sola línea con las horas indicadas o 9 por defecto.
                    if not start_day:
                        with transaction.atomic():
                            hours = (
                                base.horas_reales
                                or base.cantidad
                                or Decimal("9.00")
                            )

                            base.cantidad = hours
                            base.horas_reales = (
                                hours
                            )

                            if (
                                base.precio_unidad
                                is not None
                                and
                                base.costo_recurso_real
                                is None
                            ):
                                base.costo_recurso_real = (
                                    hours
                                    * base.precio_unidad
                                )

                            _tr_fill_common_real(
                                base,
                                tarea,
                            )

                            base.save()

                            registrar_creacion_recursos_reales_manuales(
                                recursos_reales=[
                                    base,
                                ],
                                actor=request.user,
                                operation_id=(
                                    operation_id
                                ),
                                fuente=(
                                    "tarea_recurso_"
                                    "real_create"
                                ),
                            )

                        messages.success(
                            request,
                            (
                                "Recurso real "
                                "añadido "
                                "correctamente."
                            ),
                        )

                        return redirect(
                            (
                                "planificacion_obra:"
                                "planning_tarea_detail"
                            ),
                            pk=tarea.pk,
                        )

                    if not workdays:
                        if not confirmar_no_laborable:
                            requiere_confirmar_no_laborable = True
                            form.add_error(
                                None,
                                "El rango seleccionado no contiene días laborables. Puedes crear la asignación igualmente si confirmas la operación.",
                            )
                        else:
                            from datetime import timedelta as _tr_timedelta

                            created_resources = []

                            with transaction.atomic():
                                current_day = (
                                    start_day
                                )

                                while (
                                    current_day
                                    <= end_day
                                ):
                                    hours = (
                                        base.cantidad
                                        or
                                        base.horas_reales
                                        or
                                        Decimal("0.00")
                                    )

                                    obj = (
                                        TareaRecursoReal(
                                            recurso=None,
                                            empleado=(
                                                base.empleado
                                            ),
                                            unidad="HRS",
                                            cantidad=hours,
                                            horas_reales=(
                                                hours
                                            ),
                                            precio_unidad=(
                                                base.precio_unidad
                                            ),
                                            inicio_recurso_real=(
                                                current_day
                                            ),
                                            fin_recurso_real=(
                                                current_day
                                            ),
                                            observaciones=(
                                                base.observaciones
                                            ),
                                        )
                                    )

                                    if (
                                        obj.precio_unidad
                                        is not None
                                    ):
                                        obj.costo_recurso_real = (
                                            hours
                                            * obj.precio_unidad
                                        )

                                    obj._portal_tipo_recurso_ui = (
                                        request.POST.get(
                                            "tipo_recurso_ui"
                                        )
                                        or ""
                                    )

                                    _tr_fill_common_real(
                                        obj,
                                        tarea,
                                    )

                                    raw = (
                                        obj.raw_data
                                        or {}
                                    )

                                    raw.update({
                                        (
                                            "no_laborable_"
                                            "confirmado"
                                        ): True,
                                        (
                                            "confirmado_"
                                            "desde"
                                        ): (
                                            "tarea_recurso_"
                                            "real_create"
                                        ),
                                    })

                                    obj.raw_data = raw
                                    obj.save()

                                    created_resources.append(
                                        obj
                                    )

                                    current_day = (
                                        current_day
                                        + _tr_timedelta(
                                            days=1
                                        )
                                    )

                                registrar_creacion_recursos_reales_manuales(
                                    recursos_reales=(
                                        created_resources
                                    ),
                                    actor=request.user,
                                    operation_id=(
                                        operation_id
                                    ),
                                    fuente=(
                                        "tarea_recurso_"
                                        "real_create"
                                    ),
                                )

                            messages.warning(
                                request,
                                (
                                    "Recurso real creado "
                                    "en día(s) no "
                                    "laborable(s): "
                                    f"{len(created_resources)} "
                                    "registro(s)."
                                ),
                            )

                            return redirect(
                                (
                                    "planificacion_obra:"
                                    "planning_tarea_detail"
                                ),
                                pk=tarea.pk,
                            )
                    else:
                        created_resources = []

                        manual_hours = (
                            base.cantidad
                            if (
                                base.cantidad
                                is not None
                            )
                            else
                            base.horas_reales
                        )

                        with transaction.atomic():
                            for day, hours in workdays:
                                if (
                                    manual_hours
                                    is not None
                                ):
                                    hours = (
                                        manual_hours
                                    )

                                obj = (
                                    TareaRecursoReal(
                                        recurso=None,
                                        empleado=(
                                            base.empleado
                                        ),
                                        unidad="HRS",
                                        cantidad=hours,
                                        horas_reales=(
                                            hours
                                        ),
                                        precio_unidad=(
                                            base.precio_unidad
                                        ),
                                        inicio_recurso_real=(
                                            day
                                        ),
                                        fin_recurso_real=(
                                            day
                                        ),
                                        observaciones=(
                                            base.observaciones
                                        ),
                                    )
                                )

                                if (
                                    obj.precio_unidad
                                    is not None
                                ):
                                    obj.costo_recurso_real = (
                                        hours
                                        * obj.precio_unidad
                                    )

                                obj._portal_tipo_recurso_ui = (
                                    request.POST.get(
                                        "tipo_recurso_ui"
                                    )
                                    or ""
                                )

                                _tr_fill_common_real(
                                    obj,
                                    tarea,
                                )

                                obj.save()

                                created_resources.append(
                                    obj
                                )

                            registrar_creacion_recursos_reales_manuales(
                                recursos_reales=(
                                    created_resources
                                ),
                                actor=request.user,
                                operation_id=(
                                    operation_id
                                ),
                                fuente=(
                                    "tarea_recurso_"
                                    "real_create"
                                ),
                            )

                        messages.success(
                            request,
                            (
                                "Recurso real de "
                                "empleado añadido "
                                "correctamente en "
                                f"{len(created_resources)} "
                                "día(s)."
                            ),
                        )

                        return redirect(
                            (
                                "planificacion_obra:"
                                "planning_tarea_detail"
                            ),
                            pk=tarea.pk,
                        )

            # Recurso/material/herramienta: una sola línea.
            else:
                with transaction.atomic():
                    _tr_fill_common_real(
                        base,
                        tarea,
                    )

                    base.save()

                    registrar_creacion_recursos_reales_manuales(
                        recursos_reales=[
                            base,
                        ],
                        actor=request.user,
                        operation_id=(
                            operation_id
                        ),
                        fuente=(
                            "tarea_recurso_"
                            "real_create"
                        ),
                    )

                messages.success(
                    request,
                    (
                        "Recurso real añadido "
                        "correctamente."
                    ),
                )

                return redirect(
                    (
                        "planificacion_obra:"
                        "planning_tarea_detail"
                    ),
                    pk=tarea.pk,
                )
    else:
        # PLANIFICACION_RECURSO_REAL_CREATE_FECHAS_HOY_V1
        hoy = _tr_timezone.localdate()
        form = TareaRecursoRealManualForm(
            tarea=tarea,
            initial={
                "inicio_recurso_real": hoy,
                "fin_recurso_real": hoy,
            },
        )

    mostrar_boton_no_laborable = requiere_confirmar_no_laborable

    return render(
        request,
        "planificacion_obra/tarea_recurso_form.html",
        {
            "form": form,
            "tarea": tarea,
            "titulo": "Añadir recurso real",
            "tipo": "real",
            "mostrar_boton_no_laborable": mostrar_boton_no_laborable,
            "requiere_confirmar_no_laborable": requiere_confirmar_no_laborable,
            "cancel_url": _tm_reverse("planificacion_obra:planning_tarea_detail", args=[tarea.pk]),
        },
    )

# === TAREA_RECURSOS_EDIT_DELETE_V1 ===

def _portal_manual(obj):
    raw = getattr(obj, "raw_data", None) or {}
    return raw.get("origen") == "portal_manual"


def _fill_tarea_manual_fields(tarea, request):
    obra = tarea.obra
    tarea.team = obra.team
    tarea.legacy_cod_obra = obra.legacy_cod_obra

    unidad = tarea.unidad_obra
    if unidad:
        tarea.legacy_cod_fase = unidad.legacy_cod_fase
        tarea.legacy_cod_vivienda = unidad.legacy_cod_vivienda or unidad.vivienda or ""

    if tarea.capitulo:
        tarea.legacy_capitulo = tarea.capitulo.codigo or ""

    if tarea.partida:
        if not tarea.capitulo:
            tarea.capitulo = tarea.partida.capitulo
        tarea.legacy_capitulo = tarea.capitulo.codigo or ""
        tarea.legacy_partida = tarea.partida.codigo or ""
        tarea.programacion = (tarea.partida.nombre or tarea.partida.codigo or "")[:80]
        tarea.tipo_partida = tarea.partida.tipo_partida or ""
        tarea.unidad = tarea.partida.unidad or ""

    raw = tarea.raw_data or {}
    raw.setdefault("origen", "portal_manual")
    raw.update({
        "actualizado_desde": "tarea_manual_update",
        "updated_by_user_id": getattr(request.user, "id", None),
        "updated_at": _tr_timezone.now().isoformat(),
    })
    tarea.raw_data = raw


@login_required
def tarea_manual_update(request, pk):
    from .forms import TareaObraSimpleForm

    tarea = _tr_get_tarea_for_user(request, pk)

    if not _portal_manual(tarea):
        messages.error(request, "Solo se pueden editar tareas creadas manualmente desde Portal.")
        return redirect("planificacion_obra:planning_tarea_detail", pk=tarea.pk)

    if request.method == "POST":
        form = TareaObraSimpleForm(request.POST, request=request, obra=tarea.obra, instance=tarea)
        if form.is_valid():
            tarea = form.save(commit=False)
            _fill_tarea_manual_fields(tarea, request)
            tarea.save()
            messages.success(request, "Tarea actualizada correctamente.")
            return redirect("planificacion_obra:planning_tarea_detail", pk=tarea.pk)
    else:
        form = TareaObraSimpleForm(request=request, obra=tarea.obra, instance=tarea)

    return render(
        request,
        "planificacion_obra/tarea_form.html",
        {
            "form": form,
            "obra": tarea.obra,
            "cancel_url": _tm_reverse("planificacion_obra:planning_tarea_detail", args=[tarea.pk]),
            "titulo": "Editar tarea de planificación",
        },
    )


@login_required
def tarea_manual_delete(request, pk):
    tarea = _tr_get_tarea_for_user(request, pk)

    if not _portal_manual(tarea):
        messages.error(request, "Solo se pueden eliminar tareas creadas manualmente desde Portal.")
        return redirect("planificacion_obra:planning_tarea_detail", pk=tarea.pk)

    prev_count = tarea.recursos_previstos.count()
    real_count = tarea.recursos_reales.count()

    if prev_count or real_count:
        messages.error(
            request,
            f"No se puede eliminar la tarea porque tiene {prev_count} recurso(s) inicial(es) y {real_count} recurso(s) real(es). Elimina primero las líneas.",
        )
        return redirect("planificacion_obra:planning_tarea_detail", pk=tarea.pk)

    if request.method == "POST":
        obra_pk = tarea.obra_id
        tarea.delete()
        messages.success(request, "Tarea eliminada correctamente.")
        return redirect("planificacion_obra:obra_tareas_list", pk=obra_pk)

    return render(
        request,
        "planificacion_obra/confirm_delete_simple.html",
        {
            "titulo": "Eliminar tarea",
            "objeto": tarea,
            "descripcion": f"Tarea #{tarea.pk} · {tarea.obra} · {tarea.legacy_cod_vivienda} · {tarea.legacy_planta} · {tarea.legacy_partida}",
            "cancel_url": _tm_reverse("planificacion_obra:planning_tarea_detail", args=[tarea.pk]),
        },
    )


def _get_previsto_for_user(request, pk):
    qs = TareaRecursoPrevisto.objects.select_related("team", "tarea_obra", "recurso", "unidad_obra", "partida")
    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs = qs.filter(team__in=request.user.teams.all())
    return get_object_or_404(qs, pk=pk)


def _get_real_for_user(request, pk):
    qs = TareaRecursoReal.objects.select_related("team", "tarea_obra", "recurso", "empleado", "unidad_obra", "partida")
    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs = qs.filter(team__in=request.user.teams.all())
    return get_object_or_404(qs, pk=pk)


@login_required
def tarea_recurso_previsto_update(request, pk):
    from copy import deepcopy
    from uuid import uuid4

    from django.db import transaction

    from .forms import (
        TareaRecursoPrevistoManualForm,
    )
    from .models import (
        TareaRecursoPrevisto,
    )
    from .services_recursos_previstos import (
        diff_previsto,
        registrar_edicion_previsto,
        snapshot_previsto,
    )

    obj = _get_previsto_for_user(
        request,
        pk,
    )

    tarea = obj.tarea_obra

    if not tarea:
        raise Http404(
            "Recurso previsto sin "
            "tarea vinculada."
        )

    if request.method == "POST":
        with transaction.atomic():
            locked = (
                TareaRecursoPrevisto
                .objects
                .select_for_update(
                    of=("self",)
                )
                .select_related(
                    "team",
                    "tarea_obra",
                    "unidad_obra",
                    "partida",
                    "recurso",
                )
                .get(
                    pk=obj.pk,
                    team_id=obj.team_id,
                )
            )

            anterior = snapshot_previsto(
                locked
            )

            form = (
                TareaRecursoPrevistoManualForm(
                    request.POST,
                    tarea=tarea,
                    instance=locked,
                )
            )

            if form.is_valid():
                edited = form.save(
                    commit=False
                )

                if edited.recurso:
                    edited.legacy_id_recurso = (
                        edited.recurso.legacy_id
                    )

                    if not edited.unidad:
                        edited.unidad = (
                            edited.recurso.unidad
                            or ""
                        )

                if (
                    edited.cantidad
                    is not None
                    and
                    edited.precio_unidad
                    is not None
                ):
                    edited.costo_recurso = (
                        edited.cantidad
                        * edited.precio_unidad
                    )

                preview = snapshot_previsto(
                    edited
                )

                changes = diff_previsto(
                    anterior,
                    preview,
                )

                if changes:
                    operation_id = str(
                        uuid4()
                    )

                    raw = (
                        deepcopy(
                            locked.raw_data
                        )
                        if isinstance(
                            locked.raw_data,
                            dict,
                        )
                        else {}
                    )

                    history = raw.get(
                        "ediciones_portal",
                        [],
                    )

                    if not isinstance(
                        history,
                        list,
                    ):
                        history = []

                    event = {
                        "operation_id": (
                            operation_id
                        ),
                        "updated_by_user_id": (
                            getattr(
                                request.user,
                                "pk",
                                None,
                            )
                        ),
                        "updated_at": (
                            _tr_timezone
                            .now()
                            .isoformat()
                        ),
                        "changes": changes,
                    }

                    history.append(event)

                    raw[
                        "ediciones_portal"
                    ] = history

                    raw[
                        "ultima_edicion_portal"
                    ] = event

                    edited.raw_data = raw
                    edited.save()

                    registrar_edicion_previsto(
                        previsto=edited,
                        actor=request.user,
                        anterior=anterior,
                        operation_id=(
                            operation_id
                        ),
                    )

                    messages.success(
                        request,
                        (
                            "Recurso previsto "
                            "actualizado "
                            "correctamente."
                        ),
                    )

                else:
                    messages.info(
                        request,
                        (
                            "No se detectaron "
                            "cambios en el "
                            "recurso previsto."
                        ),
                    )

                return redirect(
                    (
                        "planificacion_obra:"
                        "planning_tarea_detail"
                    ),
                    pk=tarea.pk,
                )
    else:
        form = (
            TareaRecursoPrevistoManualForm(
                tarea=tarea,
                instance=obj,
            )
        )

    return render(
        request,
        (
            "planificacion_obra/"
            "tarea_recurso_form.html"
        ),
        {
            "form": form,
            "tarea": tarea,
            "titulo": (
                "Editar recurso previsto"
            ),
            "tipo": "previsto",
            "cancel_url": _tm_reverse(
                (
                    "planificacion_obra:"
                    "planning_tarea_detail"
                ),
                args=[tarea.pk],
            ),
        },
    )


@login_required
def tarea_recurso_previsto_delete(request, pk):
    from uuid import uuid4

    from django.db import transaction

    from .models import (
        TareaRecursoPrevisto,
    )
    from .services_recursos_previstos import (
        registrar_eliminacion_previsto,
        snapshot_previsto,
    )

    obj = _get_previsto_for_user(
        request,
        pk,
    )

    tarea = obj.tarea_obra

    if not tarea:
        raise Http404(
            "Recurso previsto sin "
            "tarea vinculada."
        )

    if request.method == "POST":
        operation_id = str(
            uuid4()
        )

        with transaction.atomic():
            locked = (
                TareaRecursoPrevisto
                .objects
                .select_for_update(
                    of=("self",)
                )
                .select_related(
                    "team",
                    "tarea_obra",
                    "unidad_obra",
                    "partida",
                    "recurso",
                )
                .get(
                    pk=obj.pk,
                    team_id=obj.team_id,
                )
            )

            anterior = snapshot_previsto(
                locked
            )

            team = locked.team

            locked.delete()

            registrar_eliminacion_previsto(
                team=team,
                actor=request.user,
                anterior=anterior,
                operation_id=operation_id,
            )

        messages.success(
            request,
            (
                "Recurso previsto "
                "eliminado correctamente."
            ),
        )

        return redirect(
            (
                "planificacion_obra:"
                "planning_tarea_detail"
            ),
            pk=tarea.pk,
        )

    return render(
        request,
        (
            "planificacion_obra/"
            "confirm_delete_simple.html"
        ),
        {
            "titulo": (
                "Eliminar recurso previsto"
            ),
            "objeto": obj,
            "descripcion": (
                f"{obj.recurso or '-'} · "
                f"Cantidad "
                f"{obj.cantidad or 0} · "
                f"Coste "
                f"{obj.costo_recurso or 0}"
            ),
            "cancel_url": _tm_reverse(
                (
                    "planificacion_obra:"
                    "planning_tarea_detail"
                ),
                args=[tarea.pk],
            ),
        },
    )


@login_required
def tarea_recurso_real_update(request, pk):
    from .forms import TareaRecursoRealManualForm

    obj = _get_real_for_user(request, pk)
    tarea = obj.tarea_obra

    if not tarea:
        raise Http404("Recurso real sin tarea vinculada.")

    # PLANIFICACION_NAV_FILTROS_UPDATE_REAL_V2
    next_url = _po_safe_next_url(request.POST.get("next") or request.GET.get("next"))
    detail_url = _tm_reverse("planificacion_obra:planning_tarea_detail", args=[tarea.pk])
    detail_url_with_next = _po_url_with_next(detail_url, next_url)

    if not _portal_manual(obj):
        messages.error(request, "Solo se pueden editar recursos reales creados manualmente desde Portal.")
        return redirect(detail_url_with_next)

    if request.method == "POST":
        form = TareaRecursoRealManualForm(
            request.POST,
            tarea=tarea,
            instance=obj,
        )

        if form.is_valid():
            anterior = snapshot_recurso_real(
                obj
            )

            operation_id = (
                _tm_uuid4().hex
            )

            with transaction.atomic():
                obj = form.save(
                    commit=False
                )

                if obj.empleado:
                    obj.recurso = None
                    obj.unidad = "HRS"

                    if (
                        obj.precio_unidad
                        is None
                    ):
                        obj.precio_unidad = (
                            obj.empleado
                            .precio_hora
                        )

                    if (
                        obj.horas_reales
                        is not None
                    ):
                        obj.cantidad = (
                            obj.horas_reales
                        )

                    elif (
                        obj.cantidad
                        is not None
                    ):
                        obj.horas_reales = (
                            obj.cantidad
                        )

                    obj.legacy_personal = (
                        obj.empleado.legacy_id
                    )

                    obj.legacy_id_recurso = (
                        None
                    )

                    obj.legacy_tipo_recurso = (
                        "M.O. ADM."
                    )

                    if (
                        obj.horas_reales
                        is not None
                        and
                        obj.precio_unidad
                        is not None
                    ):
                        obj.costo_recurso_real = (
                            obj.horas_reales
                            * obj.precio_unidad
                        )

                elif obj.recurso:
                    obj.empleado = None

                    obj.legacy_id_recurso = (
                        obj.recurso.legacy_id
                    )

                    obj.legacy_personal = (
                        None
                    )

                    obj.legacy_tipo_recurso = (
                        obj.recurso.tipo
                        or ""
                    )

                    if not obj.unidad:
                        obj.unidad = (
                            obj.recurso.unidad
                            or ""
                        )

                    if (
                        obj.cantidad
                        is not None
                        and
                        obj.precio_unidad
                        is not None
                    ):
                        obj.costo_recurso_real = (
                            obj.cantidad
                            * obj.precio_unidad
                        )

                obj.costo_recurso = (
                    obj.costo_recurso_real
                )

                raw = obj.raw_data or {}

                raw.setdefault(
                    "origen",
                    "portal_manual",
                )

                raw.update({
                    "actualizado_desde": (
                        "tarea_recurso_"
                        "real_update"
                    ),
                    "updated_by_user_id": (
                        getattr(
                            request.user,
                            "id",
                            None,
                        )
                    ),
                    "updated_at": (
                        _tr_timezone
                        .now()
                        .isoformat()
                    ),
                })

                obj.raw_data = raw
                obj.save()

                registrar_cambio_recurso_real_manual(
                    recurso_real=obj,
                    actor=request.user,
                    anterior=anterior,
                    operation_id=(
                        operation_id
                    ),
                    fuente=(
                        "tarea_recurso_"
                        "real_update"
                    ),
                )

            messages.success(
                request,
                (
                    "Recurso real "
                    "actualizado "
                    "correctamente."
                ),
            )

            return redirect(
                detail_url_with_next
            )
    else:
        form = TareaRecursoRealManualForm(tarea=tarea, instance=obj)

    return render(
        request,
        "planificacion_obra/tarea_recurso_form.html",
        {
            "form": form,
            "tarea": tarea,
            "titulo": "Editar recurso real",
            "tipo": "real",
            "cancel_url": detail_url_with_next,
            "next_url": next_url,
        },
    )


@login_required
def tarea_recurso_real_delete(request, pk):
    obj = _get_real_for_user(request, pk)
    tarea = obj.tarea_obra

    if not tarea:
        raise Http404("Recurso real sin tarea vinculada.")

    if not _portal_manual(obj):
        messages.error(request, "Solo se pueden eliminar recursos reales creados manualmente desde Portal.")
        return redirect("planificacion_obra:planning_tarea_detail", pk=tarea.pk)

    if request.method == "POST":
        anterior = snapshot_recurso_real(
            obj
        )

        operation_id = (
            _tm_uuid4().hex
        )

        with transaction.atomic():
            obj.delete()

            registrar_eliminacion_recurso_real_manual(
                recurso_real=obj,
                actor=request.user,
                anterior=anterior,
                operation_id=(
                    operation_id
                ),
                fuente=(
                    "tarea_recurso_"
                    "real_delete"
                ),
            )

        messages.success(
            request,
            (
                "Recurso real "
                "eliminado "
                "correctamente."
            ),
        )

        return redirect(
            (
                "planificacion_obra:"
                "planning_tarea_detail"
            ),
            pk=tarea.pk,
        )

    return render(
        request,
        "planificacion_obra/confirm_delete_simple.html",
        {
            "titulo": "Eliminar recurso real",
            "objeto": obj,
            "descripcion": f"{obj.empleado or obj.recurso or '-'} · {obj.inicio_recurso_real or '-'} · Cantidad {obj.cantidad or 0} · Coste {obj.costo_recurso_real or 0}",
            "cancel_url": _tm_reverse("planificacion_obra:planning_tarea_detail", args=[tarea.pk]),
        },
    )

# === REALIZADO_LEGACY_UPDATE_V1 ===
@login_required
def realizado_update(request, pk):
    from decimal import Decimal
    from django.apps import apps
    from django.contrib import messages
    from django.shortcuts import get_object_or_404, redirect, render
    from django.urls import reverse
    from django.utils import timezone
    from .forms import RealizadoLegacyEditForm

    TareaRecursoReal = apps.get_model("planificacion_obra", "TareaRecursoReal")

    qs = TareaRecursoReal.objects.select_related(
        "team",
        "empleado",
        "tarea_obra",
        "tarea_obra__obra",
        "unidad_obra",
        "partida",
    )

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs = qs.filter(team__in=request.user.teams.all())

    realizado = get_object_or_404(qs, pk=pk)

    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
        or reverse("planificacion_obra:asignaciones_list")
    )

    if request.method == "POST":
        form = RealizadoLegacyEditForm(request.POST, instance=realizado, team=realizado.team)

        if form.is_valid():
            obj = form.save(commit=False)

            if obj.empleado_id:
                obj.unidad = obj.unidad or "HRS"
                obj.legacy_personal = obj.empleado.legacy_id
                obj.legacy_tipo_recurso = "M.O. ADM."

                if obj.precio_unidad is None:
                    obj.precio_unidad = obj.empleado.precio_hora or Decimal("0")

                if obj.horas_reales is not None:
                    obj.cantidad = obj.horas_reales
                elif obj.cantidad is not None:
                    obj.horas_reales = obj.cantidad

            horas = obj.horas_reales if obj.horas_reales is not None else obj.cantidad
            precio = obj.precio_unidad or Decimal("0")

            if horas is not None:
                obj.cantidad = horas
                obj.horas = horas
                obj.horas_reales = horas
                obj.costo_recurso_real = horas * precio

            if obj.inicio_recurso_real and not obj.fin_recurso_real:
                obj.fin_recurso_real = obj.inicio_recurso_real

            obj.costo_recurso = obj.costo_recurso_real

            raw = obj.raw_data or {}
            if not isinstance(raw, dict):
                raw = {"raw_data_original": str(raw)}

            raw.setdefault("origen_original", raw.get("origen") or "access")
            raw.update({
                "portal_editado": True,
                "editado_desde": "realizado_update",
                "editado_por_user_id": getattr(request.user, "id", None),
                "editado_en": timezone.now().isoformat(),
            })
            obj.raw_data = raw

            obj.save()

            messages.success(
                request,
                f"Realizado #{obj.pk} actualizado correctamente. Se conserva el origen Access y queda marcado como editado en Portal.",
            )
            return redirect(next_url)
    else:
        form = RealizadoLegacyEditForm(instance=realizado, team=realizado.team)

    empleado_precios = {}
    for emp in form.fields["empleado"].queryset:
        empleado_precios[str(emp.pk)] = float(emp.precio_hora or 0)

    return render(
        request,
        "planificacion_obra/realizado_form.html",
        {
            "form": form,
            "realizado": realizado,
            "next_url": next_url,
            "empleado_precios": empleado_precios,
            "titulo": "Editar realizado importado",
        },
    )

# PLANIFICACION_VIVIENDA_ESTADO_ALIAS_FASE1A
def vivienda_estado(request):
    # Entrada operativa para seguimiento/Gantt por vivienda.
    # Reutiliza planning_list para no duplicar lógica.
    q = request.GET.copy()

    if not q.get("vista"):
        q["vista"] = "gantt"

    if not q.get("agrupacion"):
        q["agrupacion"] = "detalle"

    if q.get("obra") and q.get("vivienda") and not q.get("limit"):
        q["limit"] = "all"

    request.GET = q
    return planning_list(request)

# PI_INFORME_HORARIO_HISTORICO_EMPTY_V4

# === PLANIFICACION_RECURSO_REAL_CONTRATADOS_V1 ===
if "_tr_fill_common_real_before_contratados_v1" not in globals():
    _tr_fill_common_real_before_contratados_v1 = _tr_fill_common_real


def _tr_fill_common_real(obj, tarea):
    """
    Wrapper seguro sobre _tr_fill_common_real:
    - Mantiene comportamiento anterior.
    - Si el empleado es CONTRATADO, marca el real como M.O. CONT.
    - Si el empleado es ADMINISTRADA, marca el real como M.O. ADM.
    """
    _tr_fill_common_real_before_contratados_v1(obj, tarea)

    empleado = getattr(obj, "empleado", None)

    if not empleado:
        return

    raw = getattr(obj, "raw_data", None) or {}
    if not isinstance(raw, dict):
        raw = {}

    tipo_empleado = getattr(empleado, "tipo", "") or ""
    legacy_id = getattr(empleado, "legacy_id", None)

    tipo_ui = (
        getattr(obj, "_portal_tipo_recurso_ui", "")
        or raw.get("tipo_recurso_ui")
        or ""
    )

    if tipo_empleado == "CONTRATADO":
        obj.legacy_tipo_recurso = tipo_ui if tipo_ui in ["M.O. CONT.", "PER. CONT."] else "M.O. CONT."
    elif tipo_empleado == "ADMINISTRADA":
        obj.legacy_tipo_recurso = "M.O. ADM."

    if legacy_id is not None:
        obj.legacy_id_recurso = legacy_id
        obj.legacy_personal = legacy_id

    obj.unidad = obj.unidad or "HRS"

    raw.update({
        "origen": raw.get("origen") or "portal_manual",
        "empleado_obra_id": empleado.id,
        "empleado_tipo": tipo_empleado,
        "tipo_recurso_ui": tipo_ui or obj.legacy_tipo_recurso,
        "legacy_tipo_recurso_resuelto": obj.legacy_tipo_recurso,
        "actualizado_desde": "PLANIFICACION_RECURSO_REAL_CONTRATADOS_V1",
    })
    obj.raw_data = raw


# === PLANIFICACION_ALMACEN_MOVIMIENTOS_PARTIDA_V1 ===

def _po_almacen_team_scope_v1(request):
    from django.apps import apps

    Team = apps.get_model("usuarios", "Team")
    active = request.session.get("active_team_id")

    if active == "all":
        if request.user.is_superuser:
            return Team.objects.all()
        if hasattr(request.user, "teams"):
            return request.user.teams.all()
        return Team.objects.none()

    if active:
        qs = Team.objects.filter(id=active)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, "teams"):
            return qs.filter(id__in=request.user.teams.values_list("id", flat=True))
        return Team.objects.none()

    if hasattr(request.user, "teams"):
        qs = request.user.teams.all()
        if qs.exists():
            return qs

    return Team.objects.none()


def _po_almacen_dec_v1(value, default="0"):
    from decimal import Decimal

    try:
        if value in ("", None):
            return Decimal(default)
        return Decimal(str(value).replace(",", "."))
    except Exception:
        return Decimal(default)


def _po_almacen_money_v1(value):
    from decimal import Decimal

    return _po_almacen_dec_v1(value).quantize(Decimal("0.0001"))


def _po_almacen_tareas_payload_v1(tareas):
    import json
    from django.utils.safestring import mark_safe

    def clean(v):
        return str(v or "").strip()

    def key(prefix, value):
        value = clean(value)
        return value if value else f"__sin_{prefix}__"

    data = []

    for t in tareas:
        unidad = getattr(t, "unidad_obra", None)
        fase_obj = getattr(unidad, "fase", None) if unidad else None

        if fase_obj:
            edificio_label = clean(fase_obj)
        elif clean(getattr(t, "legacy_cod_fase", "")):
            edificio_label = f"Fase/Edificio {t.legacy_cod_fase}"
        elif unidad:
            edificio_label = clean(getattr(unidad, "edificio", "")) or clean(unidad)
        else:
            edificio_label = ""

        vivienda_label = clean(getattr(t, "legacy_cod_vivienda", ""))
        planta_label = clean(getattr(t, "legacy_planta", ""))

        if unidad:
            vivienda_label = vivienda_label or clean(getattr(unidad, "vivienda", ""))
            planta_label = planta_label or clean(getattr(unidad, "nivel", ""))

        capitulo_label = clean(t.capitulo) if getattr(t, "capitulo_id", None) else ""
        partida_label = clean(t.partida) if getattr(t, "partida_id", None) else ""

        data.append({
            "id": t.id,
            "obra_id": t.obra_id,
            "obra": clean(t.obra),
            "edificio_key": key("edificio", getattr(t, "legacy_cod_fase", None) or edificio_label),
            "edificio": edificio_label or "Sin edificio/fase",
            "vivienda_key": key("vivienda", vivienda_label),
            "vivienda": vivienda_label or "Sin vivienda",
            "planta_key": key("planta", planta_label),
            "planta": planta_label or "Sin planta",
            "capitulo_id": t.capitulo_id or "",
            "capitulo": capitulo_label or "Sin capítulo",
            "partida_id": t.partida_id or "",
            "partida": partida_label or "Sin partida",
            "label": (
                f"{clean(t.obra)}"
                f"{' · ' + clean(unidad) if unidad else ''}"
                f"{' · ' + capitulo_label if capitulo_label else ''}"
                f"{' · ' + partida_label if partida_label else ''}"
                f" · Tarea {t.id}"
            ),
        })

    return mark_safe(json.dumps(data, ensure_ascii=False))


@login_required
def almacen_movimientos_list(request):
    from django.apps import apps
    from django.core.paginator import Paginator
    from django.db.models import Exists, OuterRef, Q
    from obra_movil.movimientos_almacen import classify_movement, origin_label, permission_allowed

    general_mode = getattr(getattr(request, "resolver_match", None), "url_name", "") == "almacen_movimientos_general"

    Mov = apps.get_model("planificacion_obra", "RecursoAlmacenMovimiento")
    Real = apps.get_model("planificacion_obra", "TareaRecursoReal")
    Almacen = apps.get_model("planificacion_obra", "AlmacenObra")
    Obra = apps.get_model("planificacion_obra", "ObraPlanificacion")

    team_scope = _po_almacen_team_scope_v1(request)

    qs = (
        Mov.objects
        .filter(team__in=team_scope)
        .select_related("team", "almacen", "recurso", "obra", "unidad_obra", "empleado", "partida")
        .annotate(tiene_real=Exists(Real.objects.filter(movimiento_almacen=OuterRef("pk"))))
        .order_by("-fecha_movimiento", "-hora_movimiento", "-created_at", "-pk")
    )

    q = (request.GET.get("q") or "").strip()
    tipo = (request.GET.get("tipo") or "").strip()
    estado = (request.GET.get("estado") or "").strip()
    almacen_id = (request.GET.get("almacen") or "").strip()
    obra_id = (request.GET.get("obra") or "").strip()
    fecha_desde = (request.GET.get("desde") or "").strip()
    fecha_hasta = (request.GET.get("hasta") or "").strip()

    if q:
        qs = qs.filter(
            Q(recurso__nombre__icontains=q) |
            Q(recurso__legacy_id__icontains=q) |
            Q(almacen__nombre__icontains=q) |
            Q(legacy_id_almacen__icontains=q) |
            Q(cod_albaran__icontains=q) |
            Q(cod_factura__icontains=q) |
            Q(observaciones__icontains=q)
        )

    if tipo:
        qs = qs.filter(tipo_movimiento=tipo)

    if almacen_id:
        qs = qs.filter(almacen_id=almacen_id)

    if obra_id:
        qs = qs.filter(obra_id=obra_id)

    if fecha_desde:
        qs = qs.filter(fecha_movimiento__gte=fecha_desde)

    if fecha_hasta:
        qs = qs.filter(fecha_movimiento__lte=fecha_hasta)

    if estado == "pendiente_partida":
        qs = qs.filter(
            tipo_movimiento__in=["SALIDA", "ROTURA"],
            en_partida=False,
            partida__isnull=True,
            tiene_real=False,
        )
    elif estado == "en_partida":
        qs = qs.filter(Q(en_partida=True) | Q(partida__isnull=False) | Q(tiene_real=True))
    elif estado == "sin_partida":
        qs = qs.filter(partida__isnull=True)

    total = qs.count()

    paginator = Paginator(qs, 80)
    page_obj = paginator.get_page(request.GET.get("page"))

    can_imputar = bool(
        request.user.is_superuser
        or request.user.has_perm("planificacion_obra.add_tarearecursoreal")
    )
    for mov in page_obj.object_list:
        mov.origin_code = classify_movement(mov)
        mov.origin_label = origin_label(mov.origin_code)
        mov.can_edit = general_mode and mov.origin_code == "MANUAL" and permission_allowed(
            request.user, "planificacion_obra.change_recursoalmacenmovimiento"
        )
        mov.can_delete = general_mode and mov.origin_code == "MANUAL" and permission_allowed(
            request.user, "planificacion_obra.delete_recursoalmacenmovimiento"
        )

    almacenes = (
        Almacen.objects
        .filter(team__in=team_scope)
        .select_related("obra")
        .order_by("obra__legacy_cod_obra", "legacy_id_almacen")
    )
    obras = Obra.objects.filter(team__in=team_scope).order_by("legacy_cod_obra", "nombre")

    return render(request, "planificacion_obra/almacen_movimientos.html", {
        "page_obj": page_obj,
        "total": total,
        "q": q,
        "tipo": tipo,
        "estado": estado,
        "almacen_id": almacen_id,
        "obra_id": obra_id,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
        "almacenes": almacenes,
        "obras": obras,
        "tipos": ["ENTRADA", "SALIDA", "CONTROL_STOCK", "ROTURA", "OTRO"],
        "querystring": request.GET.urlencode(),
        "can_imputar": can_imputar,
        "general_mode": general_mode,
    })


def almacen_movimientos_general(request):
    """Desktop canonical alias for the complete warehouse movement history."""
    return almacen_movimientos_list(request)


@login_required
def almacen_movimiento_imputar_partida(request, pk):
    from decimal import Decimal
    from django.apps import apps
    from django.contrib import messages
    from django.db import transaction
    from django.db.models import Max, Sum
    from django.shortcuts import get_object_or_404, redirect
    from django.utils import timezone

    Mov = apps.get_model("planificacion_obra", "RecursoAlmacenMovimiento")
    Real = apps.get_model("planificacion_obra", "TareaRecursoReal")
    Tarea = apps.get_model("planificacion_obra", "TareaObra")

    team_scope = _po_almacen_team_scope_v1(request)

    mov = get_object_or_404(
        Mov.objects.select_related("team", "almacen", "recurso", "obra", "unidad_obra", "partida"),
        pk=pk,
        team__in=team_scope,
    )

    if not (
        request.user.is_superuser
        or request.user.has_perm("planificacion_obra.add_tarearecursoreal")
    ):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("No tienes permiso funcional para enviar movimientos a partida.")

    back_url = request.GET.get("next") or request.POST.get("next") or "/app/planificacion-obra/almacen/movimientos/"

    ya_tiene_real = Real.objects.filter(movimiento_almacen=mov).exists()

    # PLANIFICACION_ALMACEN_ENTRADA_A_PARTIDA_V2
    if mov.tipo_movimiento not in ["ENTRADA", "SALIDA", "ROTURA"]:
        messages.error(
            request,
            "Solo se pueden enviar a partida movimientos de "
            "ENTRADA, SALIDA o ROTURA.",
        )
        return redirect(back_url)

    if mov.en_partida or mov.partida_id or ya_tiene_real:
        messages.warning(request, "Este movimiento ya está imputado o vinculado a un recurso real.")
        return redirect(back_url)

    tareas_qs = (
        Tarea.objects
        .filter(team=mov.team, partida__isnull=False)
        .select_related("obra", "unidad_obra", "unidad_obra__fase", "capitulo", "partida")
        .order_by("obra__id", "legacy_cod_fase", "legacy_cod_vivienda", "legacy_planta", "capitulo__id", "partida__id", "id")
    )

    cantidad_mov_original = abs(
        _po_almacen_dec_v1(mov.cantidad, "0")
    )
    cantidad_ya_enviada = Decimal("0")
    cantidad_pendiente_entrada = cantidad_mov_original

    if mov.tipo_movimiento == "ENTRADA":
        cantidad_ya_enviada = _po_almacen_dec_v1(
            Mov.objects
            .filter(
                team=mov.team,
                tipo_movimiento="SALIDA",
                raw_data__entrada_origen_movimiento_id=mov.id,
            )
            .aggregate(total=Sum("cantidad"))
            .get("total"),
            "0",
        )

        cantidad_pendiente_entrada = max(
            Decimal("0"),
            cantidad_mov_original - cantidad_ya_enviada,
        )

        stock_actual = _po_almacen_dec_v1(
            getattr(getattr(mov, "recurso", None), "stock", None),
            "0",
        )

        cantidad_mov = min(
            cantidad_pendiente_entrada,
            stock_actual,
        )

        if cantidad_pendiente_entrada <= 0:
            messages.warning(
                request,
                "Esta entrada ya ha sido enviada completamente "
                "a partida.",
            )
            return redirect(back_url)

        if cantidad_mov <= 0:
            messages.warning(
                request,
                "El recurso no tiene stock disponible para crear "
                "una salida a partida.",
            )
            return redirect(back_url)
    else:
        cantidad_mov = cantidad_mov_original

    precio_def = _po_almacen_dec_v1(
        getattr(getattr(mov, "recurso", None), "precio_unidad_uso", None)
        or getattr(getattr(mov, "recurso", None), "ultimo_precio_unidad", None)
        or "0"
    )
    coste_def = (cantidad_mov * precio_def).quantize(Decimal("0.0001"))

    if request.method == "POST":
        tarea_id = request.POST.get("tarea_obra_id") or ""
        fecha_raw = request.POST.get("fecha_real") or ""
        cantidad = _po_almacen_dec_v1(request.POST.get("cantidad"), "0")
        precio = _po_almacen_dec_v1(request.POST.get("precio_unidad"), "0")
        coste = _po_almacen_dec_v1(request.POST.get("costo_recurso_real"), "0")
        observaciones = (request.POST.get("observaciones") or "").strip()

        tarea = tareas_qs.filter(pk=tarea_id).first()

        if not tarea:
            messages.error(request, "Selecciona una tarea válida.")
        elif cantidad <= 0:
            messages.error(request, "La cantidad debe ser mayor que cero.")
        elif cantidad_mov > 0 and cantidad > cantidad_mov:
            messages.error(
                request,
                f"La cantidad no puede superar la disponible "
                f"({cantidad_mov}).",
            )
        elif mov.tipo_movimiento == "ENTRADA" and not mov.recurso_id:
            messages.error(
                request,
                "La entrada no tiene un recurso de almacén asociado.",
            )
        else:
            if coste == 0 and precio is not None:
                coste = (cantidad * precio).quantize(Decimal("0.0001"))

            fecha_real = timezone.localdate()
            if fecha_raw:
                try:
                    from datetime import date
                    fecha_real = date.fromisoformat(fecha_raw)
                except Exception:
                    fecha_real = timezone.localdate()

            with transaction.atomic():
                mov_locked = (
                    Mov.objects
                    .select_for_update()
                    .get(pk=mov.pk)
                )

                mov_destino = mov_locked
                es_entrada = (
                    mov_locked.tipo_movimiento == "ENTRADA"
                )

                if es_entrada:
                    recurso_model = mov_locked.recurso.__class__
                    recurso_locked = (
                        recurso_model.objects
                        .select_for_update()
                        .get(pk=mov_locked.recurso_id)
                    )

                    cantidad_total_locked = abs(
                        _po_almacen_dec_v1(
                            mov_locked.cantidad,
                            "0",
                        )
                    )

                    cantidad_enviada_locked = _po_almacen_dec_v1(
                        Mov.objects
                        .filter(
                            team=mov_locked.team,
                            tipo_movimiento="SALIDA",
                            raw_data__entrada_origen_movimiento_id=(
                                mov_locked.id
                            ),
                        )
                        .aggregate(total=Sum("cantidad"))
                        .get("total"),
                        "0",
                    )

                    cantidad_pendiente_locked = max(
                        Decimal("0"),
                        cantidad_total_locked
                        - cantidad_enviada_locked,
                    )

                    stock_locked = _po_almacen_dec_v1(
                        recurso_locked.stock,
                        "0",
                    )

                    if cantidad > cantidad_pendiente_locked:
                        messages.error(
                            request,
                            "La cantidad supera lo pendiente de "
                            "esta entrada "
                            f"({cantidad_pendiente_locked}).",
                        )
                        return redirect(back_url)

                    if cantidad > stock_locked:
                        messages.error(
                            request,
                            "La cantidad supera el stock disponible "
                            f"({stock_locked}).",
                        )
                        return redirect(back_url)

                    nuevo_stock = (
                        stock_locked - cantidad
                    ).quantize(Decimal("0.0001"))

                    next_legacy = (
                        Mov.objects
                        .filter(team=mov_locked.team)
                        .aggregate(
                            value=Max("legacy_id_movimiento")
                        )
                        .get("value")
                        or 0
                    ) + 1

                    ahora = timezone.localtime()

                    raw_salida = {
                        "source": (
                            "portal_almacen_entrada_a_partida_v2"
                        ),
                        "entrada_origen_movimiento_id": (
                            mov_locked.id
                        ),
                        "entrada_origen_legacy_id": (
                            mov_locked.legacy_id_movimiento
                        ),
                        "tarea_obra_id": tarea.id,
                        "cantidad_salida": str(cantidad),
                        "stock_anterior": str(stock_locked),
                        "stock_resultante": str(nuevo_stock),
                        "created_at": timezone.now().isoformat(),
                        "created_by_user_id": getattr(
                            request.user,
                            "id",
                            None,
                        ),
                    }

                    mov_destino = Mov.objects.create(
                        team=mov_locked.team,
                        legacy_id_movimiento=next_legacy,
                        almacen=mov_locked.almacen,
                        recurso=recurso_locked,
                        obra=tarea.obra,
                        unidad_obra=tarea.unidad_obra,
                        empleado=None,
                        partida=tarea.partida,
                        legacy_id_almacen=(
                            mov_locked.legacy_id_almacen
                            or getattr(
                                mov_locked.almacen,
                                "legacy_id_almacen",
                                None,
                            )
                            or mov_locked.almacen_id
                        ),
                        legacy_cod_recurso=(
                            mov_locked.legacy_cod_recurso
                            or getattr(
                                recurso_locked,
                                "legacy_id",
                                None,
                            )
                        ),
                        legacy_cod_obra=tarea.legacy_cod_obra,
                        legacy_cod_fase=tarea.legacy_cod_fase,
                        legacy_cod_vivienda=(
                            tarea.legacy_cod_vivienda
                        ),
                        legacy_planta=tarea.legacy_planta,
                        legacy_capitulo=tarea.legacy_capitulo,
                        legacy_partida=tarea.legacy_partida,
                        legacy_cod_personal=None,
                        unidad=(
                            mov_locked.unidad
                            or getattr(
                                recurso_locked,
                                "unidad",
                                "",
                            )
                            or ""
                        ),
                        cantidad=cantidad,
                        quedan=nuevo_stock,
                        fecha_movimiento=fecha_real,
                        hora_movimiento=ahora.time().replace(
                            microsecond=0
                        ),
                        tipo_movimiento="SALIDA",
                        tipo_movimiento_raw="SALIDA",
                        cod_proveedor=(
                            mov_locked.cod_proveedor or ""
                        ),
                        cod_albaran=(
                            mov_locked.cod_albaran or ""
                        ),
                        linea=mov_locked.linea,
                        cod_factura=(
                            mov_locked.cod_factura or ""
                        ),
                        en_partida=True,
                        vehiculo="",
                        kilometraje=None,
                        observaciones=(
                            observaciones
                            or "Salida a partida desde entrada de "
                            f"almacén {mov_locked.id}"
                        ),
                        raw_data=raw_salida,
                    )

                    recurso_locked.stock = nuevo_stock

                    if hasattr(recurso_locked, "control_stock"):
                        recurso_locked.control_stock = True

                    recurso_locked.save()

                real = Real(
                    recurso=mov_locked.recurso,
                    empleado=None,
                    movimiento_almacen=mov_destino,
                    legacy_id_movimiento_almacen=(
                        mov_destino.legacy_id_movimiento
                    ),
                    unidad=(
                        mov_destino.unidad
                        or getattr(
                            mov_locked.recurso,
                            "unidad",
                            "",
                        )
                        or ""
                    ),
                    cantidad=cantidad,
                    precio_unidad=precio,
                    costo_recurso=coste,
                    costo_recurso_real=coste,
                    inicio_recurso_real=fecha_real,
                    fin_recurso_real=fecha_real,
                    cod_albaran=(
                        mov_locked.cod_albaran or ""
                    ),
                    num_linea_albaran=mov_locked.linea,
                    cod_factura=(
                        mov_locked.cod_factura or ""
                    ),
                    observaciones=(
                        observaciones
                        or "Imputado desde movimiento de almacén "
                        f"{mov_destino.id}"
                    ),
                )

                _tr_fill_common_real(real, tarea)

                real.movimiento_almacen = mov_destino
                real.legacy_id_movimiento_almacen = (
                    mov_destino.legacy_id_movimiento
                )
                real.legacy_tipo_recurso = (
                    getattr(
                        mov_locked.recurso,
                        "tipo",
                        "",
                    )
                    or ""
                )
                real.legacy_id_recurso = getattr(
                    mov_locked.recurso,
                    "legacy_id",
                    None,
                )
                real.unidad = (
                    real.unidad
                    or mov_destino.unidad
                    or getattr(
                        mov_locked.recurso,
                        "unidad",
                        "",
                    )
                    or ""
                )

                raw_real = real.raw_data or {}
                raw_real.update({
                    "origen": (
                        "almacen_movimiento_imputar_partida"
                    ),
                    "movimiento_almacen_id": mov_destino.id,
                    "movimiento_entrada_origen_id": (
                        mov_locked.id if es_entrada else None
                    ),
                    "legacy_id_movimiento_almacen": (
                        mov_destino.legacy_id_movimiento
                    ),
                    "tipo_movimiento_origen": (
                        mov_locked.tipo_movimiento
                    ),
                    "tarea_obra_id": tarea.id,
                    "created_at": timezone.now().isoformat(),
                    "created_by_user_id": getattr(
                        request.user,
                        "id",
                        None,
                    ),
                })
                real.raw_data = raw_real
                real.save()

                raw_destino = (
                    mov_destino.raw_data
                    if isinstance(mov_destino.raw_data, dict)
                    else {}
                )
                raw_destino["_planificacion_recurso_real"] = {
                    "marker": (
                        "PLANIFICACION_ALMACEN_"
                        "ENTRADA_A_PARTIDA_V2"
                    ),
                    "created_at": timezone.now().isoformat(),
                    "tarea_obra_id": tarea.id,
                    "tarea_recurso_real_id": real.id,
                    "cantidad": str(cantidad),
                    "precio_unidad": str(precio),
                    "coste_real": str(coste),
                }
                mov_destino.raw_data = raw_destino

                if es_entrada:
                    mov_destino.save(
                        update_fields=[
                            "raw_data",
                            "updated_at",
                        ]
                    )

                    total_enviado = (
                        cantidad_enviada_locked + cantidad
                    )
                    pendiente_final = max(
                        Decimal("0"),
                        cantidad_total_locked - total_enviado,
                    )

                    raw_entrada = (
                        mov_locked.raw_data
                        if isinstance(
                            mov_locked.raw_data,
                            dict,
                        )
                        else {}
                    )

                    salidas_ids = raw_entrada.get(
                        "salidas_a_partida_ids"
                    )

                    if not isinstance(salidas_ids, list):
                        salidas_ids = []

                    if mov_destino.id not in salidas_ids:
                        salidas_ids.append(mov_destino.id)

                    raw_entrada.update({
                        "cantidad_en_partidas": (
                            str(total_enviado)
                        ),
                        "cantidad_pendiente_partidas": (
                            str(pendiente_final)
                        ),
                        "salidas_a_partida_ids": salidas_ids,
                        "ultima_salida_a_partida_id": (
                            mov_destino.id
                        ),
                        "ultima_tarea_obra_id": tarea.id,
                        "ultima_imputacion_at": (
                            timezone.now().isoformat()
                        ),
                    })

                    mov_locked.raw_data = raw_entrada
                    mov_locked.en_partida = (
                        pendiente_final <= 0
                    )
                    mov_locked.save(
                        update_fields=[
                            "en_partida",
                            "raw_data",
                            "updated_at",
                        ]
                    )
                else:
                    mov_locked.obra = tarea.obra
                    mov_locked.unidad_obra = tarea.unidad_obra
                    mov_locked.partida = tarea.partida
                    mov_locked.legacy_cod_obra = (
                        tarea.legacy_cod_obra
                    )
                    mov_locked.legacy_cod_fase = (
                        tarea.legacy_cod_fase
                    )
                    mov_locked.legacy_cod_vivienda = (
                        tarea.legacy_cod_vivienda
                    )
                    mov_locked.legacy_planta = (
                        tarea.legacy_planta
                    )
                    mov_locked.legacy_capitulo = (
                        tarea.legacy_capitulo
                    )
                    mov_locked.legacy_partida = (
                        tarea.legacy_partida
                    )
                    mov_locked.en_partida = True
                    mov_locked.raw_data = raw_destino

                    mov_locked.save(
                        update_fields=[
                            "obra",
                            "unidad_obra",
                            "partida",
                            "legacy_cod_obra",
                            "legacy_cod_fase",
                            "legacy_cod_vivienda",
                            "legacy_planta",
                            "legacy_capitulo",
                            "legacy_partida",
                            "en_partida",
                            "raw_data",
                            "updated_at",
                        ]
                    )

            if mov.tipo_movimiento == "ENTRADA":
                messages.success(
                    request,
                    f"Salida {mov_destino.id} creada desde la "
                    f"entrada {mov.id}; recurso real {real.id} "
                    "imputado y stock actualizado.",
                )
            else:
                messages.success(
                    request,
                    f"Movimiento {mov.id} imputado a partida y "
                    f"recurso real {real.id} creado.",
                )
            return redirect(back_url)

    return render(request, "planificacion_obra/almacen_movimiento_imputar.html", {
        "mov": mov,
        "tareas_json": _po_almacen_tareas_payload_v1(tareas_qs),
        "back_url": back_url,
        "fecha_hoy": timezone.localdate(),
        "cantidad_def": cantidad_mov,
        "precio_def": precio_def,
        "coste_def": coste_def,
    })

# =============================================================================
# RECURSOS_OBRA_LIST_V1
# Consulta consolidada de recursos reales, previstos y movimientos de almacén.
# Vista exclusivamente de lectura.
# =============================================================================
@login_required
def recursos_obra_list(request):
    from datetime import timedelta
    from decimal import Decimal
    from types import SimpleNamespace
    from urllib.parse import quote

    from django.apps import apps
    from django.db.models import Count, Q, Sum
    from django.shortcuts import render
    from django.urls import reverse
    from django.utils import timezone
    from django.utils.dateparse import parse_date

    ObraPlanificacion = apps.get_model(
        "planificacion_obra",
        "ObraPlanificacion",
    )
    FaseObra = apps.get_model(
        "planificacion_obra",
        "FaseObra",
    )
    UnidadObra = apps.get_model(
        "planificacion_obra",
        "UnidadObra",
    )
    TareaObra = apps.get_model(
        "planificacion_obra",
        "TareaObra",
    )
    CapituloCatalogo = apps.get_model(
        "planificacion_obra",
        "CapituloCatalogo",
    )
    PartidaCatalogo = apps.get_model(
        "planificacion_obra",
        "PartidaCatalogo",
    )
    RecursoCatalogo = apps.get_model(
        "planificacion_obra",
        "RecursoCatalogo",
    )
    TareaRecursoReal = apps.get_model(
        "planificacion_obra",
        "TareaRecursoReal",
    )
    TareaRecursoPrevisto = apps.get_model(
        "planificacion_obra",
        "TareaRecursoPrevisto",
    )
    RecursoAlmacenMovimiento = apps.get_model(
        "planificacion_obra",
        "RecursoAlmacenMovimiento",
    )

    RESOURCE_TYPES = (
        "MATERIAL",
        "MAQUINARIA",
        "HERRAMIENTA",
        "E.P.I.S.",
        "PORTES",
    )

    def by_team(queryset):
        if (
            not request.user.is_superuser
            and hasattr(request.user, "teams")
        ):
            return queryset.filter(
                team__in=request.user.teams.all()
            )

        return queryset

    def first_value(*values):
        for value in values:
            if value not in (None, ""):
                return value
        return ""

    def decimal_value(value):
        try:
            return Decimal(str(value or 0))
        except Exception:
            return Decimal("0")

    def related_labels(obj):
        tarea = getattr(obj, "tarea_obra", None)

        unidad = (
            getattr(obj, "unidad_obra", None)
            or getattr(tarea, "unidad_obra", None)
        )

        partida = (
            getattr(obj, "partida", None)
            or getattr(tarea, "partida", None)
        )

        capitulo = (
            getattr(partida, "capitulo", None)
            or getattr(tarea, "capitulo", None)
        )

        obra = (
            getattr(tarea, "obra", None)
            or getattr(unidad, "obra", None)
            or getattr(obj, "obra", None)
        )

        fase_codigo = first_value(
            getattr(obj, "legacy_cod_fase", None),
            getattr(tarea, "legacy_cod_fase", None),
            getattr(unidad, "legacy_cod_fase", None),
        )

        fase_nombre = first_value(
            getattr(unidad, "edificio", ""),
            getattr(
                getattr(unidad, "fase", None),
                "nombre",
                "",
            ),
        )

        vivienda = first_value(
            getattr(obj, "legacy_cod_vivienda", ""),
            getattr(tarea, "legacy_cod_vivienda", ""),
            getattr(unidad, "vivienda", ""),
        )

        planta = first_value(
            getattr(obj, "legacy_planta", ""),
            getattr(tarea, "legacy_planta", ""),
        )

        capitulo_codigo = first_value(
            getattr(capitulo, "codigo", ""),
            getattr(obj, "legacy_capitulo", ""),
            getattr(tarea, "legacy_capitulo", ""),
        )

        capitulo_nombre = first_value(
            getattr(capitulo, "nombre", ""),
            capitulo_codigo,
        )

        partida_codigo = first_value(
            getattr(partida, "codigo", ""),
            getattr(obj, "legacy_partida", ""),
            getattr(obj, "legacy_cod_partida", ""),
            getattr(tarea, "legacy_partida", ""),
        )

        partida_nombre = first_value(
            getattr(partida, "nombre", ""),
            partida_codigo,
        )

        tarea_label = first_value(
            getattr(tarea, "programacion", ""),
            getattr(partida, "nombre", ""),
            str(tarea) if tarea else "",
        )

        # RECURSOS_OBRA_RETURN_CONTEXT_V1_2
        # Conservar pestaña, periodo y filtros al abrir el detalle.
        tarea_url = ""

        if tarea:
            detail_url = reverse(
                "planificacion_obra:planning_tarea_detail",
                args=[tarea.pk],
            )

            return_url = quote(
                request.get_full_path(),
                safe="",
            )

            tarea_url = (
                f"{detail_url}?next={return_url}"
            )

        fase_label = str(fase_codigo or "—")

        if fase_nombre:
            fase_label = (
                f"{fase_codigo} · {fase_nombre}"
                if fase_codigo
                else fase_nombre
            )

        return {
            "tarea": tarea,
            "tarea_url": tarea_url,
            "tarea_label": tarea_label or "—",
            "obra": obra,
            "obra_label": str(obra) if obra else "—",
            "fase_codigo": fase_codigo,
            "fase_label": fase_label,
            "vivienda": vivienda or "—",
            "planta": planta or "—",
            "capitulo_codigo": capitulo_codigo,
            "capitulo_nombre": capitulo_nombre or "—",
            "partida_codigo": partida_codigo,
            "partida_nombre": partida_nombre or "—",
        }

    today = timezone.localdate()

    tab = (
        request.GET.get("tab")
        or "real"
    ).strip().lower()

    if tab not in {
        "real",
        "previsto",
        "movimientos",
    }:
        tab = "real"

    fecha_desde_raw = (
        request.GET.get("fecha_desde")
        or ""
    ).strip()

    fecha_hasta_raw = (
        request.GET.get("fecha_hasta")
        or ""
    ).strip()

    # PLANIFICACION_RECURSOS_TABS_DEFAULT_V1_1
    # Sin filtros visibles al entrar. La consulta inicial muestra
    # internamente los recursos reales de los últimos 30 días.
    fecha_desde_dt = (
        parse_date(fecha_desde_raw)
        if fecha_desde_raw
        else None
    )

    fecha_hasta_dt = (
        parse_date(fecha_hasta_raw)
        if fecha_hasta_raw
        else None
    )

    if fecha_desde_raw and not fecha_desde_dt:
        fecha_desde_raw = ""

    if fecha_hasta_raw and not fecha_hasta_dt:
        fecha_hasta_raw = ""

    if (
        fecha_desde_dt
        and fecha_hasta_dt
        and fecha_desde_dt > fecha_hasta_dt
    ):
        fecha_desde_dt, fecha_hasta_dt = (
            fecha_hasta_dt,
            fecha_desde_dt,
        )

    if fecha_desde_dt and fecha_hasta_dt:
        consulta_desde_dt = fecha_desde_dt
        consulta_hasta_dt = fecha_hasta_dt

    elif fecha_desde_dt:
        consulta_desde_dt = fecha_desde_dt
        consulta_hasta_dt = today

    elif fecha_hasta_dt:
        consulta_hasta_dt = fecha_hasta_dt
        consulta_desde_dt = (
            fecha_hasta_dt - timedelta(days=30)
        )

    else:
        consulta_hasta_dt = today
        consulta_desde_dt = (
            today - timedelta(days=30)
        )

    fecha_desde = (
        fecha_desde_dt.isoformat()
        if fecha_desde_dt
        else ""
    )

    fecha_hasta = (
        fecha_hasta_dt.isoformat()
        if fecha_hasta_dt
        else ""
    )

    obra_id = (
        request.GET.get("obra")
        or ""
    ).strip()

    fase = (
        request.GET.get("edificio")
        or request.GET.get("fase")
        or ""
    ).strip()

    vivienda = (
        request.GET.get("vivienda")
        or ""
    ).strip()

    planta = (
        request.GET.get("planta")
        or ""
    ).strip()

    capitulo_id = (
        request.GET.get("capitulo")
        or ""
    ).strip()

    partida_id = (
        request.GET.get("partida")
        or ""
    ).strip()

    tipo = (
        request.GET.get("tipo")
        or ""
    ).strip().upper()

    q_recurso = (
        request.GET.get("q_recurso")
        or ""
    ).strip()

    if tipo not in RESOURCE_TYPES:
        tipo = ""

    obras = (
        by_team(
            ObraPlanificacion.objects
            .select_related("team")
            .all()
        )
        .order_by("codigo", "id")
    )

    selected_obra = None

    if obra_id.isdigit():
        selected_obra = obras.filter(
            pk=int(obra_id)
        ).first()

    if not selected_obra:
        obra_id = ""
        fase = ""
        vivienda = ""
        planta = ""
        capitulo_id = ""
        partida_id = ""

    edificios = []
    viviendas = []
    plantas = []
    capitulos = CapituloCatalogo.objects.none()
    partidas = PartidaCatalogo.objects.none()

    task_options = by_team(
        TareaObra.objects
        .select_related(
            "unidad_obra",
            "capitulo",
            "partida",
        )
        .all()
    )

    if selected_obra:
        task_options = task_options.filter(
            obra=selected_obra
        )

        fase_qs = (
            by_team(
                FaseObra.objects.filter(
                    obra=selected_obra,
                )
            )
            .order_by(
                "legacy_cod_fase",
                "nombre",
            )
        )

        edificios = [
            SimpleNamespace(
                id=str(item.legacy_cod_fase),
                label=(
                    f"{item.legacy_cod_fase} · {item.nombre}"
                ),
            )
            for item in fase_qs
        ]

        unidades_qs = by_team(
            UnidadObra.objects.filter(
                obra=selected_obra,
            )
        )

        if fase:
            unidades_qs = unidades_qs.filter(
                legacy_cod_fase=fase,
            )

            task_options = task_options.filter(
                legacy_cod_fase=fase,
            )

        viviendas_map = {}

        for legacy_vivienda, vivienda_real in (
            unidades_qs
            .values_list(
                "legacy_cod_vivienda",
                "vivienda",
            )
            .order_by(
                "legacy_cod_vivienda",
                "vivienda",
                "id",
            )
        ):
            codigo = str(
                legacy_vivienda
                or vivienda_real
                or ""
            ).strip()

            if codigo:
                viviendas_map.setdefault(
                    codigo,
                    codigo,
                )

        viviendas = [
            SimpleNamespace(
                id=codigo,
                label=codigo,
            )
            for codigo in sorted(viviendas_map)
        ]

        if vivienda:
            task_options = task_options.filter(
                Q(legacy_cod_vivienda=vivienda)
                | Q(unidad_obra__vivienda=vivienda)
            )

        plantas = [
            SimpleNamespace(
                id=value,
                label=value,
            )
            for value in (
                task_options
                .exclude(legacy_planta="")
                .exclude(legacy_planta__isnull=True)
                .values_list(
                    "legacy_planta",
                    flat=True,
                )
                .distinct()
                .order_by("legacy_planta")
            )
        ]

        if planta:
            task_options = task_options.filter(
                legacy_planta=planta,
            )

        capitulos = (
            by_team(
                CapituloCatalogo.objects.filter(
                    tareas__in=task_options,
                )
            )
            .distinct()
            .order_by(
                "codigo",
                "nombre",
            )
        )

        partida_task_options = task_options

        if capitulo_id.isdigit():
            partida_task_options = (
                partida_task_options.filter(
                    capitulo_id=int(capitulo_id),
                )
            )

        partidas = (
            by_team(
                PartidaCatalogo.objects
                .select_related("capitulo")
                .filter(
                    tareas__in=partida_task_options,
                )
            )
            .distinct()
            .order_by(
                "codigo",
                "nombre",
            )
        )

    recursos_base = by_team(
        RecursoCatalogo.objects.filter(
            tipo__in=RESOURCE_TYPES,
        )
    )

    if selected_obra:
        recursos_base = recursos_base.filter(
            team=selected_obra.team,
        )

    tipo_choices = list(
        recursos_base
        .values_list("tipo", flat=True)
        .distinct()
        .order_by("tipo")
    )

    rows = []
    total_registros = 0
    total_mostrados = 0
    kpis = {}

    def apply_resource_filter(queryset):
        if tipo:
            queryset = queryset.filter(
                recurso__tipo=tipo,
            )

        if q_recurso:
            resource_q = Q(
                recurso__nombre__icontains=q_recurso
            )

            if q_recurso.isdigit():
                resource_q |= Q(
                    recurso__legacy_id=int(q_recurso)
                )

            queryset = queryset.filter(resource_q)

        return queryset

    def apply_real_structure(queryset):
        if selected_obra:
            queryset = queryset.filter(
                Q(tarea_obra__obra=selected_obra)
                | Q(unidad_obra__obra=selected_obra)
                | Q(
                    legacy_cod_obra=(
                        selected_obra.legacy_cod_obra
                    )
                )
            )

        if fase:
            queryset = queryset.filter(
                legacy_cod_fase=fase,
            )

        if vivienda:
            queryset = queryset.filter(
                Q(legacy_cod_vivienda=vivienda)
                | Q(unidad_obra__vivienda=vivienda)
                | Q(
                    tarea_obra__unidad_obra__vivienda=(
                        vivienda
                    )
                )
            )

        if planta:
            queryset = queryset.filter(
                legacy_planta=planta,
            )

        if capitulo_id.isdigit():
            queryset = queryset.filter(
                Q(
                    tarea_obra__capitulo_id=(
                        int(capitulo_id)
                    )
                )
                | Q(
                    partida__capitulo_id=(
                        int(capitulo_id)
                    )
                )
            )

        if partida_id.isdigit():
            queryset = queryset.filter(
                Q(partida_id=int(partida_id))
                | Q(
                    tarea_obra__partida_id=(
                        int(partida_id)
                    )
                )
            )

        return queryset

    if tab == "real":
        queryset = (
            by_team(
                TareaRecursoReal.objects
                .select_related(
                    "team",
                    "recurso",
                    "tarea_obra",
                    "tarea_obra__obra",
                    "tarea_obra__unidad_obra",
                    "tarea_obra__capitulo",
                    "tarea_obra__partida",
                    "unidad_obra",
                    "unidad_obra__fase",
                    "partida",
                    "partida__capitulo",
                    "movimiento_almacen",
                )
            )
            .filter(
                recurso__isnull=False,
                recurso__tipo__in=RESOURCE_TYPES,
                inicio_recurso_real__gte=consulta_desde_dt,
                inicio_recurso_real__lte=consulta_hasta_dt,
            )
        )

        queryset = apply_real_structure(queryset)
        queryset = apply_resource_filter(queryset)
        queryset = queryset.distinct()

        total_registros = queryset.count()

        summary = queryset.aggregate(
            recursos=Count(
                "recurso_id",
                distinct=True,
            ),
            importe=Sum("costo_recurso_real"),
        )

        for item in queryset.order_by(
            "-inicio_recurso_real",
            "-id",
        )[:500]:
            labels = related_labels(item)

            cantidad = decimal_value(item.cantidad)
            precio = decimal_value(item.precio_unidad)

            importe = (
                decimal_value(item.costo_recurso_real)
                if item.costo_recurso_real is not None
                else cantidad * precio
            )

            rows.append(
                SimpleNamespace(
                    id=item.id,
                    fecha=item.inicio_recurso_real,
                    fecha_fin=(
                        item.fin_recurso_real
                        or item.inicio_recurso_real
                    ),
                    recurso=item.recurso,
                    recurso_tipo=(
                        item.recurso.tipo
                        or item.legacy_tipo_recurso
                        or "—"
                    ),
                    cantidad=cantidad,
                    unidad=(
                        item.unidad
                        or item.recurso.unidad
                        or "—"
                    ),
                    precio=precio,
                    importe=importe,
                    albaran=item.cod_albaran or "",
                    factura=item.cod_factura or "",
                    **labels,
                )
            )

        kpis = {
            "principal_label": "Recursos reales",
            "principal_value": total_registros,
            "secundario_label": "Recursos distintos",
            "secundario_value": summary.get(
                "recursos"
            ) or 0,
            "importe_label": "Coste real registrado",
            "importe_value": decimal_value(
                summary.get("importe")
            ),
        }

    elif tab == "previsto":
        queryset = (
            by_team(
                TareaRecursoPrevisto.objects
                .select_related(
                    "team",
                    "recurso",
                    "tarea_obra",
                    "tarea_obra__obra",
                    "tarea_obra__unidad_obra",
                    "tarea_obra__capitulo",
                    "tarea_obra__partida",
                    "unidad_obra",
                    "unidad_obra__fase",
                    "partida",
                    "partida__capitulo",
                )
            )
            .filter(
                recurso__isnull=False,
                recurso__tipo__in=RESOURCE_TYPES,
            )
        )

        if selected_obra:
            queryset = queryset.filter(
                Q(tarea_obra__obra=selected_obra)
                | Q(unidad_obra__obra=selected_obra)
                | Q(
                    legacy_cod_obra=(
                        selected_obra.legacy_cod_obra
                    )
                )
            )

        if fase:
            queryset = queryset.filter(
                legacy_cod_fase=fase,
            )

        if vivienda:
            queryset = queryset.filter(
                Q(legacy_cod_vivienda=vivienda)
                | Q(unidad_obra__vivienda=vivienda)
                | Q(
                    tarea_obra__unidad_obra__vivienda=(
                        vivienda
                    )
                )
            )

        if planta:
            queryset = queryset.filter(
                legacy_planta=planta,
            )

        if capitulo_id.isdigit():
            queryset = queryset.filter(
                Q(
                    tarea_obra__capitulo_id=(
                        int(capitulo_id)
                    )
                )
                | Q(
                    partida__capitulo_id=(
                        int(capitulo_id)
                    )
                )
            )

        if partida_id.isdigit():
            queryset = queryset.filter(
                Q(partida_id=int(partida_id))
                | Q(
                    tarea_obra__partida_id=(
                        int(partida_id)
                    )
                )
            )

        effective_period = (
            Q(
                fecha_estimada_entrega__gte=(
                    consulta_desde_dt
                ),
                fecha_estimada_entrega__lte=(
                    consulta_hasta_dt
                ),
            )
            | (
                Q(fecha_estimada_entrega__isnull=True)
                & Q(
                    tarea_obra__inicio_tarea__lte=(
                        consulta_hasta_dt
                    )
                )
                & (
                    Q(
                        tarea_obra__fin_tarea__gte=(
                            consulta_desde_dt
                        )
                    )
                    | Q(
                        tarea_obra__fin_tarea__isnull=True
                    )
                )
            )
        )

        queryset = queryset.filter(effective_period)
        queryset = apply_resource_filter(queryset)
        queryset = queryset.distinct()

        total_registros = queryset.count()

        summary = queryset.aggregate(
            recursos=Count(
                "recurso_id",
                distinct=True,
            ),
            importe=Sum("costo_recurso"),
        )

        sin_fecha_entrega = queryset.filter(
            fecha_estimada_entrega__isnull=True
        ).count()

        for item in queryset.order_by(
            "fecha_estimada_entrega",
            "tarea_obra__inicio_tarea",
            "legacy_cod_vivienda",
            "id",
        )[:500]:
            labels = related_labels(item)
            tarea = item.tarea_obra

            cantidad = decimal_value(item.cantidad)
            precio = decimal_value(item.precio_unidad)

            importe = (
                decimal_value(item.costo_recurso)
                if item.costo_recurso is not None
                else cantidad * precio
            )

            if item.fecha_estimada_entrega:
                fecha_inicio = (
                    item.fecha_estimada_entrega
                )
                fecha_fin = (
                    item.fecha_estimada_entrega
                )
                fecha_origen = "Entrega"
            else:
                fecha_inicio = getattr(
                    tarea,
                    "inicio_tarea",
                    None,
                )
                fecha_fin = getattr(
                    tarea,
                    "fin_tarea",
                    None,
                )
                fecha_origen = "Plan de tarea"

            rows.append(
                SimpleNamespace(
                    id=item.id,
                    fecha=fecha_inicio,
                    fecha_fin=fecha_fin,
                    fecha_origen=fecha_origen,
                    recurso=item.recurso,
                    recurso_tipo=(
                        item.recurso.tipo or "—"
                    ),
                    cantidad=cantidad,
                    unidad=(
                        item.unidad
                        or item.recurso.unidad
                        or "—"
                    ),
                    precio=precio,
                    importe=importe,
                    albaran="",
                    factura="",
                    **labels,
                )
            )

        kpis = {
            "principal_label": "Líneas previstas",
            "principal_value": total_registros,
            "secundario_label": "Recursos distintos",
            "secundario_value": summary.get(
                "recursos"
            ) or 0,
            "importe_label": "Coste previsto",
            "importe_value": decimal_value(
                summary.get("importe")
            ),
            "sin_fecha_entrega": sin_fecha_entrega,
        }

    else:
        queryset = (
            by_team(
                RecursoAlmacenMovimiento.objects
                .select_related(
                    "team",
                    "almacen",
                    "recurso",
                    "obra",
                    "unidad_obra",
                    "unidad_obra__fase",
                    "partida",
                    "partida__capitulo",
                )
                .prefetch_related(
                    "recursos_reales_tarea",
                )
            )
            .filter(
                recurso__isnull=False,
                recurso__tipo__in=RESOURCE_TYPES,
                fecha_movimiento__gte=consulta_desde_dt,
                fecha_movimiento__lte=consulta_hasta_dt,
            )
        )

        if selected_obra:
            queryset = queryset.filter(
                Q(obra=selected_obra)
                | Q(unidad_obra__obra=selected_obra)
                | Q(
                    legacy_cod_obra=(
                        selected_obra.legacy_cod_obra
                    )
                )
            )

        if fase:
            queryset = queryset.filter(
                legacy_cod_fase=fase,
            )

        if vivienda:
            queryset = queryset.filter(
                Q(legacy_cod_vivienda=vivienda)
                | Q(unidad_obra__vivienda=vivienda)
            )

        if planta:
            queryset = queryset.filter(
                legacy_planta=planta,
            )

        if capitulo_id.isdigit():
            queryset = queryset.filter(
                Q(
                    partida__capitulo_id=(
                        int(capitulo_id)
                    )
                )
                | Q(
                    legacy_capitulo=(
                        str(capitulo_id)
                    )
                )
            )

        if partida_id.isdigit():
            queryset = queryset.filter(
                partida_id=int(partida_id)
            )

        queryset = apply_resource_filter(queryset)
        queryset = queryset.distinct()

        total_registros = queryset.count()

        all_movement_ids = list(
            queryset.values_list(
                "id",
                flat=True,
            )
        )

        linked_movement_ids = set(
            TareaRecursoReal.objects
            .filter(
                movimiento_almacen_id__in=(
                    all_movement_ids
                )
            )
            .values_list(
                "movimiento_almacen_id",
                flat=True,
            )
        )

        entradas = queryset.filter(
            tipo_movimiento="ENTRADA"
        ).count()

        salidas = queryset.filter(
            tipo_movimiento="SALIDA"
        ).count()

        for item in queryset.order_by(
            "-fecha_movimiento",
            "-hora_movimiento",
            "-id",
        )[:500]:
            labels = related_labels(item)

            linked_reals = list(
                item.recursos_reales_tarea.all()
            )

            rows.append(
                SimpleNamespace(
                    id=item.id,
                    fecha=item.fecha_movimiento,
                    hora=item.hora_movimiento,
                    tipo_movimiento=(
                        item.tipo_movimiento
                        or item.tipo_movimiento_raw
                        or "—"
                    ),
                    almacen=(
                        str(item.almacen)
                        if item.almacen_id
                        else "—"
                    ),
                    recurso=item.recurso,
                    recurso_tipo=(
                        item.recurso.tipo or "—"
                    ),
                    cantidad=decimal_value(
                        item.cantidad
                    ),
                    unidad=(
                        item.unidad
                        or item.recurso.unidad
                        or "—"
                    ),
                    albaran=item.cod_albaran or "",
                    factura=item.cod_factura or "",
                    imputado=bool(linked_reals),
                    real_ids=[
                        real.id
                        for real in linked_reals
                    ],
                    **labels,
                )
            )

        kpis = {
            "principal_label": "Movimientos",
            "principal_value": total_registros,
            "secundario_label": "Entradas / Salidas",
            "secundario_value": (
                f"{entradas} / {salidas}"
            ),
            "importe_label": "Imputados a recurso real",
            "importe_value": len(
                linked_movement_ids
            ),
        }

    total_mostrados = len(rows)

    context = {
        "tab": tab,
        "rows": rows,
        "total_registros": total_registros,
        "total_mostrados": total_mostrados,
        "kpis": kpis,
        "obras": obras,
        "selected_obra": selected_obra,
        "edificios": edificios,
        "viviendas": viviendas,
        "plantas": plantas,
        "capitulos": capitulos,
        "partidas": partidas,
        "tipo_choices": tipo_choices,
        "resource_types": RESOURCE_TYPES,
        "filtros": {
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "obra": obra_id,
            "edificio": fase,
            "fase": fase,
            "vivienda": vivienda,
            "planta": planta,
            "capitulo": capitulo_id,
            "partida": partida_id,
            "tipo": tipo,
            "q_recurso": q_recurso,
        },
    }

    return render(
        request,
        "planificacion_obra/recursos_obra_list.html",
        context,
    )

# =============================================================================
# TAREA_RECURSO_REAL_REUBICAR_V1_2
# Corrección auditada del destino de una imputación real.
# =============================================================================
@login_required
def tarea_recurso_real_reubicar(request, pk):
    from django.apps import apps
    from django.contrib import messages
    from django.shortcuts import (
        get_object_or_404,
        redirect,
        render,
    )
    from django.db import transaction
    from django.urls import reverse

    from planificacion_obra.activity_recursos_reales import (
        registrar_reubicacion_recursos_reales_manuales,
    )
    from planificacion_obra.services_reubicacion import (
        ReubicacionError,
        SCOPE_DOCUMENT_CURRENT_TASK,
        SCOPE_SINGLE,
        document_info,
        execute_relocation,
        preview_relocation,
        scope_queryset,
    )

    Real = apps.get_model(
        "planificacion_obra",
        "TareaRecursoReal",
    )

    Tarea = apps.get_model(
        "planificacion_obra",
        "TareaObra",
    )

    real_queryset = (
        Real.objects
        .select_related(
            "team",
            "recurso",
            "tarea_obra",
            "tarea_obra__obra",
            "tarea_obra__unidad_obra",
            "tarea_obra__capitulo",
            "tarea_obra__partida",
            "unidad_obra",
            "partida",
            "movimiento_almacen",
        )
    )

    if (
        not request.user.is_superuser
        and hasattr(request.user, "teams")
    ):
        real_queryset = real_queryset.filter(
            team__in=request.user.teams.all()
        )

    real = get_object_or_404(
        real_queryset,
        pk=pk,
    )

    source_task = real.tarea_obra

    if not source_task:
        messages.error(
            request,
            "La imputación no está vinculada a una tarea.",
        )

        return redirect(
            "planificacion_obra:planning_list"
        )

    next_url = _po_safe_next_url(
        request.POST.get("next")
        or request.GET.get("next")
    )

    source_detail_url = reverse(
        "planificacion_obra:planning_tarea_detail",
        args=[source_task.pk],
    )

    source_detail_url = _po_url_with_next(
        source_detail_url,
        next_url,
    )

    candidate_tasks = (
        Tarea.objects
        .select_related(
            "obra",
            "unidad_obra",
            "capitulo",
            "partida",
        )
        .filter(
            team_id=real.team_id,
            obra_id=source_task.obra_id,
            partida_id=source_task.partida_id,
            unidad_obra__isnull=False,
        )
        .exclude(pk=source_task.pk)
        .order_by(
            "legacy_cod_fase",
            "legacy_cod_vivienda",
            "legacy_planta",
            "id",
        )
    )

    document = document_info(real)
    grouped_count = 1

    try:
        grouped_count = scope_queryset(
            real,
            SCOPE_DOCUMENT_CURRENT_TASK,
        ).count()

    except ReubicacionError:
        grouped_count = 1

    grouped_available = bool(
        grouped_count > 1
        and document.get("origin")
        and document.get("document_id")
    )

    selected_scope = (
        request.POST.get("scope")
        or SCOPE_SINGLE
    ).strip()

    selected_target_id = (
        request.POST.get("target_task")
        or ""
    ).strip()

    reason = (
        request.POST.get("reason")
        or ""
    ).strip()

    action = (
        request.POST.get("action")
        or ""
    ).strip()

    preview = None
    errors = []

    if request.method == "POST":
        if selected_scope not in {
            SCOPE_SINGLE,
            SCOPE_DOCUMENT_CURRENT_TASK,
        }:
            errors.append(
                "Selecciona un alcance válido."
            )

        if (
            selected_scope
            == SCOPE_DOCUMENT_CURRENT_TASK
            and not grouped_available
        ):
            errors.append(
                "No existe un grupo documental válido "
                "para esta imputación."
            )

        if not selected_target_id.isdigit():
            errors.append(
                "Selecciona una tarea de destino."
            )

        if len(reason) < 8:
            errors.append(
                "Indica un motivo suficientemente "
                "descriptivo."
            )

        if not errors:
            try:
                preview = preview_relocation(
                    real_id=real.id,
                    target_task_id=int(
                        selected_target_id
                    ),
                    scope=selected_scope,
                    lock=False,
                )

            except (
                ReubicacionError,
                Tarea.DoesNotExist,
                Real.DoesNotExist,
            ) as exc:
                errors.append(str(exc))

        if (
            action == "confirm"
            and not errors
            and preview
        ):
            confirmation = (
                request.POST.get("confirmation")
                or ""
            ).strip()

            if confirmation != "REUBICAR":
                errors.append(
                    "Escribe exactamente REUBICAR "
                    "para confirmar."
                )

            else:
                try:
                    with transaction.atomic():
                        locked_preview = preview_relocation(
                            real_id=real.id,
                            target_task_id=int(
                                selected_target_id
                            ),
                            scope=selected_scope,
                            lock=True,
                        )

                        anteriores = list(
                            locked_preview["items"]
                        )

                        result = execute_relocation(
                            real_id=real.id,
                            target_task_id=int(
                                selected_target_id
                            ),
                            scope=selected_scope,
                            reason=reason,
                            user=request.user,
                        )

                        posteriores = list(
                            real_queryset.filter(
                                pk__in=result["real_ids"]
                            ).order_by("pk")
                        )

                        registrar_reubicacion_recursos_reales_manuales(
                            anteriores=anteriores,
                            posteriores=posteriores,
                            actor=request.user,
                            operation_id=(
                                result["operation_id"]
                            ),
                            reason=reason,
                            result=result,
                        )

                except (
                    ReubicacionError,
                    Tarea.DoesNotExist,
                    Real.DoesNotExist,
                ) as exc:
                    errors.append(str(exc))

                else:
                    messages.success(
                        request,
                        (
                            f"{result['count']} "
                            f"imputación(es) reubicadas. "
                            f"Operación "
                            f"{result['operation_id']}."
                        ),
                    )

                    target_detail_url = reverse(
                        (
                            "planificacion_obra:"
                            "planning_tarea_detail"
                        ),
                        args=[
                            result["target"]["task_id"]
                        ],
                    )

                    target_detail_url = (
                        _po_url_with_next(
                            target_detail_url,
                            next_url,
                        )
                    )

                    return redirect(
                        target_detail_url
                    )

    return render(
        request,
        (
            "planificacion_obra/"
            "tarea_recurso_real_reubicar.html"
        ),
        {
            "real": real,
            "source_task": source_task,
            "candidate_tasks": candidate_tasks,
            "document": document,
            "grouped_count": grouped_count,
            "grouped_available": grouped_available,
            "selected_scope": selected_scope,
            "selected_target_id": selected_target_id,
            "reason": reason,
            "preview": preview,
            "errors": errors,
            "next_url": next_url,
            "source_detail_url": source_detail_url,
            "scope_single": SCOPE_SINGLE,
            "scope_grouped": (
                SCOPE_DOCUMENT_CURRENT_TASK
            ),
        },
    )

@login_required
def tarea_recurso_previsto_reubicar(
    request,
    pk,
):
    from django import forms

    from .models import TareaObra
    from .services_recursos_previstos import (
        PrevistoActionError,
        execute_previsto_relocation,
    )

    previsto = _get_previsto_for_user(
        request,
        pk,
    )

    source_task = previsto.tarea_obra

    if not source_task:
        raise Http404(
            "Recurso previsto sin "
            "tarea vinculada."
        )

    candidates = (
        TareaObra.objects
        .filter(
            team_id=previsto.team_id,
            obra_id=source_task.obra_id,
            partida_id=(
                source_task.partida_id
            ),
            unidad_obra__isnull=False,
        )
        .exclude(pk=source_task.pk)
        .select_related(
            "obra",
            "unidad_obra",
            "capitulo",
            "partida",
        )
        .order_by(
            "legacy_cod_fase",
            "legacy_cod_vivienda",
            "legacy_planta",
            "pk",
        )
    )

    class RelocationForm(forms.Form):
        target_task = (
            forms.ModelChoiceField(
                queryset=candidates,
                label="Tarea de destino",
                empty_label=(
                    "Selecciona destino"
                ),
            )
        )

        reason = forms.CharField(
            label="Motivo",
            min_length=8,
            widget=forms.Textarea(
                attrs={"rows": 3}
            ),
        )

    form = RelocationForm(
        request.POST or None
    )

    form.fields[
        "target_task"
    ].label_from_instance = (
        lambda task: (
            f"Viv. "
            f"{task.legacy_cod_vivienda or '-'}"
            f" · {task.legacy_planta or '-'}"
            f" · "
            f"{task.legacy_capitulo or '-'}"
            f" · {task.legacy_partida or '-'}"
            f" · tarea #{task.pk}"
        )
    )

    if (
        request.method == "POST"
        and form.is_valid()
    ):
        target_task = (
            form.cleaned_data[
                "target_task"
            ]
        )

        try:
            result = (
                execute_previsto_relocation(
                    previsto_id=previsto.pk,
                    target_task_id=(
                        target_task.pk
                    ),
                    reason=(
                        form.cleaned_data[
                            "reason"
                        ]
                    ),
                    user=request.user,
                )
            )

        except PrevistoActionError as exc:
            form.add_error(
                None,
                str(exc),
            )

        else:
            messages.success(
                request,
                (
                    "Recurso previsto "
                    "reubicado correctamente."
                ),
            )

            return redirect(
                (
                    "planificacion_obra:"
                    "planning_tarea_detail"
                ),
                pk=result[
                    "target_task_id"
                ],
            )

    return render(
        request,
        (
            "planificacion_obra/"
            "tarea_recurso_previsto_"
            "reubicar.html"
        ),
        {
            "form": form,
            "previsto": previsto,
            "source_task": source_task,
            "cancel_url": _tm_reverse(
                (
                    "planificacion_obra:"
                    "planning_tarea_detail"
                ),
                args=[source_task.pk],
            ),
        },
    )



# ============================================================
# ASIGNACION_AVANCE_ACUMULADO_VIEWS_V1_1
# ============================================================

def _asignacion_aplicar_avance_tarea(
    *,
    form,
    asignacion,
):
    from decimal import Decimal

    tarea = form.cleaned_data.get("tarea_obra")

    if tarea is None:
        raise ValueError(
            "La asignación necesita una tarea."
        )

    porcentaje = Decimal(
        str(
            form.cleaned_data[
                "porcentaje_completado"
            ]
        )
    ).quantize(Decimal("0.01"))

    asignacion.tarea_obra = tarea

    if not asignacion.unidad_obra_id:
        asignacion.unidad_obra = (
            tarea.unidad_obra
        )

    if not asignacion.capitulo_id:
        asignacion.capitulo = tarea.capitulo

    if not asignacion.partida_id:
        asignacion.partida = tarea.partida

    cantidad = form.cleaned_data.get(
        "cantidad_ejecutada"
    )

    asignacion.cantidad_ejecutada = cantidad

    if cantidad is None:
        asignacion.unidad_ejecutada = ""
    else:
        asignacion.unidad_ejecutada = (
            tarea.unidad
            or getattr(
                tarea.partida,
                "unidad",
                "",
            )
            or ""
        )

    tarea.porcentaje_completado = porcentaje

    tarea.save(
        update_fields=[
            "porcentaje_completado",
            "sincronizado_en",
        ]
    )


@login_required
def asignacion_tarea_avance_api(
    request,
    pk,
):
    from django.http import JsonResponse

    tarea = _tr_get_tarea_for_user(
        request,
        pk,
    )

    porcentaje = (
        tarea.porcentaje_completado
        if tarea.porcentaje_completado
        is not None
        else 0
    )

    unidad = (
        tarea.unidad
        or getattr(
            tarea.partida,
            "unidad",
            "",
        )
        or ""
    )

    return JsonResponse(
        {
            "id": tarea.pk,
            "porcentaje_completado": (
                str(porcentaje)
            ),
            "unidad": unidad,
            "cantidad_prevista": (
                str(tarea.cantidad)
                if tarea.cantidad is not None
                else ""
            ),
        }
    )


from django.views.decorators.http import (
    require_POST as _avance_require_POST,
)


@login_required
@_avance_require_POST
def tarea_avance_update(
    request,
    pk,
):
    from decimal import Decimal, InvalidOperation

    from django.contrib import messages
    from django.shortcuts import redirect

    tarea = _tr_get_tarea_for_user(
        request,
        pk,
    )

    raw = (
        request.POST.get(
            "porcentaje_completado"
        )
        or ""
    ).strip().replace(",", ".")

    next_url = (
        _po_safe_next_url(
            request.POST.get("next")
        )
        or _po_planning_base_url()
    )

    try:
        nuevo = Decimal(raw).quantize(
            Decimal("0.01")
        )
    except (InvalidOperation, ValueError):
        messages.error(
            request,
            "El porcentaje indicado no es válido.",
        )
        return redirect(next_url)

    if nuevo < 0 or nuevo > 100:
        messages.error(
            request,
            "El porcentaje debe estar entre 0 y 100.",
        )
        return redirect(next_url)

    actual = (
        tarea.porcentaje_completado
        if tarea.porcentaje_completado
        is not None
        else Decimal("0.00")
    )

    if nuevo < actual:
        messages.error(
            request,
            (
                f"La tarea ya está al {actual} %. "
                "El porcentaje no puede disminuir."
            ),
        )
        return redirect(next_url)

    tarea.porcentaje_completado = nuevo

    tarea.save(
        update_fields=[
            "porcentaje_completado",
            "sincronizado_en",
        ]
    )

    messages.success(
        request,
        f"Avance actualizado al {nuevo} %.",
    )

    return redirect(next_url)


# ============================================================
# ASIGNACION_UNIDAD_PRODUCCION_MANUAL_SAVE_V1
# Sustituye la implementación anterior del helper.
# Las vistas de alta y edición resuelven este nombre en tiempo
# de ejecución y utilizarán esta versión.
# ============================================================

def _asignacion_aplicar_avance_tarea(
    *,
    form,
    asignacion,
):
    from decimal import Decimal

    tarea = form.cleaned_data.get("tarea_obra")

    if tarea is None:
        raise ValueError(
            "La asignación necesita una tarea."
        )

    porcentaje = Decimal(
        str(
            form.cleaned_data[
                "porcentaje_completado"
            ]
        )
    ).quantize(Decimal("0.01"))

    asignacion.tarea_obra = tarea

    if not asignacion.unidad_obra_id:
        asignacion.unidad_obra = (
            tarea.unidad_obra
        )

    if not asignacion.capitulo_id:
        asignacion.capitulo = tarea.capitulo

    if not asignacion.partida_id:
        asignacion.partida = tarea.partida

    cantidad = form.cleaned_data.get(
        "cantidad_ejecutada"
    )

    unidad = (
        form.cleaned_data.get(
            "unidad_ejecutada"
        )
        or ""
    ).strip()

    asignacion.cantidad_ejecutada = cantidad

    asignacion.unidad_ejecutada = (
        unidad
        if cantidad is not None
        else ""
    )

    tarea.porcentaje_completado = porcentaje

    tarea.save(
        update_fields=[
            "porcentaje_completado",
            "sincronizado_en",
        ]
    )
