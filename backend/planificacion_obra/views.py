from decimal import Decimal
from django.contrib import messages
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
    active_team = get_active_team(request)

    obras = filter_by_active_team(ObraPlanificacion.objects.all(), request)
    empleados = filter_by_active_team(EmpleadoObra.objects.all(), request)
    unidades = filter_by_active_team(UnidadObra.objects.all(), request)
    capitulos = filter_by_active_team(CapituloCatalogo.objects.all(), request)
    partidas = filter_by_active_team(PartidaCatalogo.objects.all(), request)
    recursos = filter_by_active_team(RecursoCatalogo.objects.all(), request)
    almacenes = filter_by_active_team(AlmacenObra.objects.all(), request)
    tareas_obra = filter_by_active_team(TareaObra.objects.all(), request)
    asignaciones = filter_by_active_team(AsignacionObra.objects.all(), request)

    informes_planificacion = []
    if REPORTS_DIR.exists():
        for report in sorted(
            REPORTS_DIR.glob("*.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:20]:
            nombre = report.name
            if nombre.startswith("audit_planificacion_obra_"):
                tipo = "Auditoría general"
            elif nombre.startswith("coste_real_por_obra_tipo_"):
                tipo = "Coste real por obra y tipo"
            elif nombre.startswith("desviaciones_obra_"):
                tipo = "Desviaciones ejecutivas"
            else:
                tipo = "Informe CSV"

            informes_planificacion.append({
                "nombre": nombre,
                "tipo": tipo,
                "tamano_kb": round(report.stat().st_size / 1024, 1),
                "fecha": datetime.fromtimestamp(report.stat().st_mtime),
            })

    context = {
        "active_team": active_team,
        "modo_todas": active_team is None,
        "informes_planificacion": informes_planificacion,
        "obras_count": obras.count(),
        "empleados_count": empleados.count(),
        "unidades_count": unidades.count(),
        "capitulos_count": capitulos.count(),
        "partidas_count": partidas.count(),
        "recursos_count": recursos.count(),
        "almacenes_count": almacenes.count(),
        "tareas_obra_count": tareas_obra.count(),
        "asignaciones_count": asignaciones.count(),
        "ultimas_asignaciones": asignaciones.select_related(
            "empleado", "unidad_obra", "capitulo", "partida", "team"
        )[:10],
    }

    return render(request, "planificacion_obra/index.html", context)



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

    qs = (
        filter_by_active_team(TareaObra.objects.filter(obra=obra), request)
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
            Q(legacy_cod_vivienda__icontains=q)
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
        filter_by_active_team(FaseObra.objects.filter(obra=obra), request)
        .order_by("legacy_cod_fase", "nombre")
    )

    capitulos = (
        filter_by_active_team(CapituloCatalogo.objects.filter(tareas__obra=obra), request)
        .distinct()
        .order_by("codigo", "nombre")
    )

    partidas = (
        filter_by_active_team(PartidaCatalogo.objects.filter(tareas__obra=obra), request)
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


@login_required
def asignaciones_list(request):
    from types import SimpleNamespace
    from django.apps import apps
    from datetime import timedelta
    from django.db.models import Q
    from django.utils import timezone
    from django.utils.dateparse import parse_date

    AsignacionObra = apps.get_model("planificacion_obra", "AsignacionObra")
    TareaRecursoReal = apps.get_model("planificacion_obra", "TareaRecursoReal")
    ObraPlanificacion = apps.get_model("planificacion_obra", "ObraPlanificacion")
    Empleado = apps.get_model("rrhh", "Empleado")

    today = timezone.localdate()
    HISTORICO_REAL_DEFAULT_DAYS = 30

    fecha = request.GET.get("fecha") or ""
    fecha_desde = request.GET.get("fecha_desde") or ""
    fecha_hasta = request.GET.get("fecha_hasta") or ""
    obra_id = request.GET.get("obra") or ""
    empleado_id = request.GET.get("empleado") or ""
    estado = request.GET.get("estado") or ""

    fecha_dt = parse_date(fecha) if fecha else None
    fecha_desde_dt = parse_date(fecha_desde) if fecha_desde else None
    fecha_hasta_dt = parse_date(fecha_hasta) if fecha_hasta else None

    def by_team(qs):
        if not request.user.is_superuser and hasattr(request.user, "teams"):
            return qs.filter(team__in=request.user.teams.all())
        return qs

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
    ).exclude(
        legacy_id_recurso_tarea__gte=300000,
    )

    qs_real = by_team(qs_real)

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
            partida=r.legacy_partida or "-",
            estado="REALIZADO",
            estado_label="Realizado",
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

    empleados_plan_ids = by_team(
        AsignacionObra.objects.all()
    ).order_by().values_list("empleado_id", flat=True)

    # Añadimos también empleados legacy vinculados a históricos reales.
    # Importante: order_by() vacío evita arrastrar el ordering pesado del modelo.
    empleados_legacy_ids = by_team(
        TareaRecursoReal.objects.filter(empleado__rrhh_empleado_id__isnull=False)
    ).order_by().values_list("empleado__rrhh_empleado_id", flat=True).distinct()

    empleados = Empleado.objects.filter(
        Q(id__in=empleados_plan_ids) | Q(id__in=empleados_legacy_ids)
    )

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        empleados = empleados.filter(team__in=request.user.teams.all())

    empleados = empleados.distinct().order_by("nombre_completo", "id")

    estado_choices = [
        ("PENDIENTE", "Pendiente"),
        ("REALIZADO", "Realizado"),
    ]

    context = {
        "asignaciones": rows_limitadas,
        "asignaciones_count": len(rows),
        "total_asignaciones": len(rows),
        "total_mostradas": len(rows_limitadas),
        "obras": obras,
        "empleados": empleados,
        "estado_choices": estado_choices,
        "filtros": {
            "fecha": fecha,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
            "obra": obra_id,
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
            asignacion.save()
            messages.success(request, "Asignación de personal creada correctamente.")
            return redirect("planificacion_obra:asignaciones_list")
    else:
        form = AsignacionObraForm(request_user=request.user, initial=initial)

    context = {
        "form": form,
        "titulo": "Nueva asignación de personal",
    }
    return render(request, "planificacion_obra/asignacion_form.html", context)



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
        "capitulo": clean(realizado.legacy_capitulo),
        "partida": clean(realizado.legacy_partida),
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

    try:
        recurso_real = realizar_asignacion_obra(asignacion, user=request.user)
    except RealizacionAsignacionError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        messages.error(request, f"No se pudo marcar como realizado: {exc}")
    else:
        messages.success(
            request,
            f"Asignación #{asignacion.id} marcada como realizada. Recurso real #{recurso_real.id} creado/actualizado."
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

    modo_ajuste_realizado = (
        request.GET.get("ajustar_realizado") == "1"
        or request.POST.get("modo") == "ajustar_realizado"
    )

    today = timezone.localdate()

    def build_context(form, values=None):
        values = values or {}
        return {
            "form": form,
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

        asignacion.fecha_inicio = fecha_inicio
        asignacion.fecha_fin = fecha_fin
        asignacion.hora_inicio = hora_inicio
        asignacion.hora_fin = hora_fin
        asignacion.save(update_fields=["fecha_inicio", "fecha_fin", "hora_inicio", "hora_fin", "actualizado_en"])

        messages.success(request, "Fecha y horario real ajustados. Ahora puedes marcar la asignación como realizada.")
        return redirect("planificacion_obra:asignacion_detail", pk=asignacion.pk)

    if request.method == "POST":
        form = AsignacionObraForm(request.POST, instance=asignacion, request_user=request.user)
        if form.is_valid():
            obj = form.save(commit=False)

            if getattr(obj, "team_id", None) is None and getattr(obj, "tarea_obra", None):
                obj.team = obj.tarea_obra.team

            obj.save()
            messages.success(request, "Asignación actualizada correctamente.")
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
        asignacion.delete()
        messages.success(request, "Asignación eliminada correctamente.")
        return redirect("planificacion_obra:asignaciones_list")

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
    ).exclude(
        legacy_id_recurso_tarea__gte=300000,
    )

    qs_real = by_team(qs_real)

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
        partida_txt = r.legacy_partida or "-"
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
    ).exclude(
        legacy_id_recurso_tarea__gte=300000,
    )

    if not request.user.is_superuser and hasattr(request.user, "teams"):
        qs_real = qs_real.filter(team__in=request.user.teams.all())

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
        partida_txt = r.legacy_partida or "-"

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

    fecha_desde = parse_date(request.GET.get("desde"), today)
    fecha_hasta = parse_date(request.GET.get("hasta"), today + timedelta(days=21))

    if fecha_hasta < fecha_desde:
        fecha_hasta = fecha_desde

    if (fecha_hasta - fecha_desde).days > 120:
        fecha_hasta = fecha_desde + timedelta(days=120)

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

    for a in qs.order_by(
        "fecha_inicio",
        "hora_inicio",
        "unidad_obra__edificio",
        "unidad_obra__vivienda",
        "tarea_obra__legacy_planta",
        "empleado_id",
        "capitulo__codigo",
        "partida__codigo",
    )[:1000]:
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
    ).exclude(
        legacy_id_recurso_tarea__gte=300000,
    )

    qs_real = by_team(qs_real)

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
    )[:1500]:
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
            "horario": "Histórico",
            "horas": round(horas, 2),
            "empleado": str(r.empleado) if r.empleado_id else "-",
            "obra": obra_txt,
            "edificio": getattr(r.unidad_obra, "edificio", "") if r.unidad_obra_id else "",
            "vivienda": vivienda_label(getattr(r.unidad_obra, "vivienda", None) if r.unidad_obra_id else r.legacy_cod_vivienda),
            "planta": r.legacy_planta or "-",
            "capitulo": r.legacy_capitulo or "-",
            "partida": r.legacy_partida or "-",
            "estado": "Realizado",
            "origen": "Realizado",
        })

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

    return render(request, "planificacion_obra/asignaciones_informe.html", {
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
        estructura_qs = by_team(TareaObra.objects.filter(obra=selected_obra))

        viviendas_qs = estructura_qs
        if fase:
            viviendas_qs = viviendas_qs.filter(legacy_cod_fase=fase)

        # La vivienda se ofrece como desplegable, preferentemente tras seleccionar fase.
        if fase:
            viviendas = list(
                viviendas_qs
                .exclude(legacy_cod_vivienda__isnull=True)
                .exclude(legacy_cod_vivienda="")
                .values_list("legacy_cod_vivienda", flat=True)
                .distinct()
                .order_by("legacy_cod_vivienda")
            )

        plantas_qs = estructura_qs
        if fase:
            plantas_qs = plantas_qs.filter(legacy_cod_fase=fase)
        if vivienda:
            plantas_qs = plantas_qs.filter(legacy_cod_vivienda=vivienda)

        # Planta funcional de tarea, no nivel físico de vivienda.
        plantas = list(
            plantas_qs
            .exclude(legacy_planta__isnull=True)
            .exclude(legacy_planta="")
            .values_list("legacy_planta", flat=True)
            .distinct()
            .order_by("legacy_planta")
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

            for r in rows:
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
                    "late": bool(
                        getattr(r, "fin_real", None)
                        and getattr(r, "fin_tarea", None)
                        and r.fin_real > r.fin_tarea
                    ),
                    "warnings_count": len(getattr(r, "warnings", None) or []),
                })
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

    return render(request, "planificacion_obra/planning_list.html", context)



@_planning_login_required
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

    context = {
        "tarea": tarea,
        "snapshot": snapshot,
        "recursos_previstos": recursos_previstos,
        "recursos_reales": recursos_reales,
        "next_url": request.GET.get("next") or "/app/planificacion-obra/planning/",
    }

    return render(request, "planificacion_obra/planning_tarea_detail.html", context)

