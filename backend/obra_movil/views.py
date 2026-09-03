from decimal import Decimal

from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max, Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from planificacion_obra.models import (
    AlmacenObra,
    AsignacionObra,
    ObraPlanificacion,
    RecursoAlmacenMovimiento,
    RecursoCatalogo,
    TareaRecursoReal,
)
from planificacion_obra.utils import filter_by_active_team, get_active_team

from .forms import ProduccionMovilFiltroForm, ProduccionMovilForm
from .forms_almacen import AlmacenMovimientoFiltroForm, AlmacenMovimientoMovilForm
from .forms_almacen_rapido import AlmacenRapidoForm
from .forms_stock import ControlStockMovilForm, StockMovilFiltroForm
from .forms_incidencias import IncidenciaMovilFiltroForm, IncidenciaObraMovilForm
from obra_movil.models import IncidenciaObraMovil


MOBILE_LEGACY_RECURSO_REAL_OFFSET = 900000000


def _scoped(qs, request):
    return filter_by_active_team(qs, request)


def _dashboard_context(request):
    hoy = timezone.localdate()
    active_team = get_active_team(request)

    obras_qs = _scoped(ObraPlanificacion.objects.all(), request)
    almacenes_qs = _scoped(AlmacenObra.objects.all(), request)
    movimientos_qs = _scoped(RecursoAlmacenMovimiento.objects.all(), request)
    asignaciones_qs = _scoped(AsignacionObra.objects.all(), request)
    reales_qs = _scoped(TareaRecursoReal.objects.all(), request)
    recursos_qs = _scoped(RecursoCatalogo.objects.all(), request)

    # OBRA_MOVIL_DASH_MOV_HISTORICO_V1
    #
    # El dashboard distingue:
    # - cuándo se registró el movimiento (created_at);
    # - cuándo ocurrió realmente (fecha_movimiento).
    #
    # Por defecto muestra los últimos REGISTRADOS, para que una operación
    # histórica introducida hoy sea visible inmediatamente.
    from datetime import timedelta
    from django.core.paginator import Paginator

    mov_period = (request.GET.get("mov_period") or "recent").strip().lower()

    mov_period_choices = [
        ("recent", "Últimos registrados"),
        ("7", "Últimos 7 días"),
        ("30", "Últimos 30 días"),
        ("90", "Últimos 90 días"),
        ("nodate", "Sin fecha"),
        ("all", "Todos"),
    ]

    valid_mov_periods = {value for value, _label in mov_period_choices}
    if mov_period not in valid_mov_periods:
        mov_period = "recent"

    ultimos_movimientos_qs = movimientos_qs.select_related(
        "almacen",
        "recurso",
        "obra",
        "unidad_obra",
        "partida",
        "empleado",
    )

    if mov_period == "recent":
        ultimos_movimientos_qs = (
            ultimos_movimientos_qs
            .order_by("-created_at", "-pk")
        )

    elif mov_period in {"7", "30", "90"}:
        dias = int(mov_period)
        desde = hoy - timedelta(days=dias)

        ultimos_movimientos_qs = (
            ultimos_movimientos_qs
            .filter(
                fecha_movimiento__gte=desde,
                fecha_movimiento__lte=hoy,
            )
            .order_by(
                "-fecha_movimiento",
                "-hora_movimiento",
                "-pk",
            )
        )

    elif mov_period == "nodate":
        ultimos_movimientos_qs = (
            ultimos_movimientos_qs
            .filter(fecha_movimiento__isnull=True)
            .order_by("-created_at", "-pk")
        )

    else:
        ultimos_movimientos_qs = (
            ultimos_movimientos_qs
            .order_by(
                "-fecha_movimiento",
                "-hora_movimiento",
                "-created_at",
                "-pk",
            )
        )

    movimientos_dashboard_total = ultimos_movimientos_qs.count()

    movimientos_dashboard_paginator = Paginator(
        ultimos_movimientos_qs,
        20,
    )

    movimientos_dashboard_page = (
        movimientos_dashboard_paginator
        .get_page(request.GET.get("mov_page") or 1)
    )

    ultimos_movimientos = movimientos_dashboard_page.object_list

    ultimos_reales = (
        reales_qs
        .select_related("tarea_obra", "tarea_obra__obra", "recurso", "empleado", "unidad_obra", "partida")
        .order_by("-inicio_recurso_real", "-id")[:8]
    )

    return {
        "page_title": "Obra móvil",
        "today": hoy,
        "active_team": active_team,
        "modo_todas": active_team is None,
        "obras_count": obras_qs.count(),
        "almacenes_count": almacenes_qs.count(),
        "movimientos_hoy_count": movimientos_qs.filter(fecha_movimiento=hoy).count(),
        "asignaciones_hoy_count": asignaciones_qs.filter(
            fecha_inicio__lte=hoy,
            fecha_fin__gte=hoy,
        ).count(),
        "produccion_hoy_count": reales_qs.filter(
            inicio_recurso_real__lte=hoy,
            fin_recurso_real__gte=hoy,
        ).count(),
        "recursos_control_stock_count": recursos_qs.filter(control_stock=True).count(),
        "ultimos_movimientos": ultimos_movimientos,
        "mov_period": mov_period,
        "mov_period_choices": mov_period_choices,
        "movimientos_dashboard_total": movimientos_dashboard_total,
        "movimientos_dashboard_page": movimientos_dashboard_page,
        "ultimos_reales": ultimos_reales,
    }


@login_required
def index(request):
    return render(request, "obra_movil/index.html", _dashboard_context(request))


def _section(request, key, title, subtitle, icon, primary_url=None, secondary_url=None):
    context = _dashboard_context(request)
    context.update({
        "section_key": key,
        "section_title": title,
        "section_subtitle": subtitle,
        "section_icon": icon,
        "primary_url": primary_url,
        "secondary_url": secondary_url,
    })
    return render(request, "obra_movil/section.html", context)



# OBRA_MOVIL_UX0_PWA_V1

def pwa_manifest(request):
    return JsonResponse({
        "name": "Obra móvil INTASA",
        "short_name": "Obra móvil",
        "description": "Operaciones de obra desde móvil o tablet.",
        "start_url": "/app/obra-movil/",
        "scope": "/app/obra-movil/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#0f172a",
        "theme_color": "#0d6efd",
        "icons": [
            {
                "src": "/app/obra-movil/icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            }
        ],
        "categories": ["business", "productivity"],
    })


def pwa_icon(request):
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="112" fill="#0d6efd"/>
  <path d="M112 344h288v48H112z" fill="#fff" opacity=".95"/>
  <path d="M144 312h224V136c0-17.7-14.3-32-32-32H176c-17.7 0-32 14.3-32 32v176z" fill="#fff" opacity=".95"/>
  <path d="M184 168h144v32H184zM184 232h144v32H184z" fill="#0d6efd"/>
  <path d="M104 384h304v32H104z" fill="#dbeafe"/>
</svg>"""
    return HttpResponse(svg, content_type="image/svg+xml")


@login_required
def instalar_home(request):
    context = _dashboard_context(request)
    context.update({
        "page_title": "Instalar Obra móvil",
        "obra_movil_url": request.build_absolute_uri(reverse("obra_movil:index")),
        "login_url": request.build_absolute_uri("/accounts/login/?next=/app/obra-movil/"),
    })
    return render(request, "obra_movil/instalar.html", context)


@login_required
def produccion_home(request):
    return _section(
        request,
        "produccion",
        "Producción",
        "Alta móvil de producción real ejecutada en obra.",
        "bi-person-check",
        reverse("obra_movil:produccion_nueva"),
        "/app/planificacion-obra/asignaciones/",
    )


def _codigo(obj, default=""):
    if not obj:
        return default
    return (
        getattr(obj, "codigo", None)
        or getattr(obj, "cod_partida", None)
        or getattr(obj, "cod_capitulo", None)
        or getattr(obj, "nombre", None)
        or default
    )


def _tipo_recurso_empleado(empleado):
    raw = getattr(empleado, "raw_data", None) or {}
    if isinstance(raw, dict):
        tipo = raw.get("Tipo") or raw.get("tipo")
        if tipo:
            return str(tipo).strip()
    return "M.O. ADM." if empleado.tipo == "ADMINISTRADA" else "M.O. CONT."


def _next_mobile_legacy_id(team):
    current = (
        TareaRecursoReal.objects
        .filter(team=team, legacy_id_recurso_tarea__gte=MOBILE_LEGACY_RECURSO_REAL_OFFSET)
        .aggregate(m=Max("legacy_id_recurso_tarea"))
        .get("m")
    )
    candidate = (current or MOBILE_LEGACY_RECURSO_REAL_OFFSET) + 1

    while TareaRecursoReal.objects.filter(team=team, legacy_id_recurso_tarea=candidate).exists():
        candidate += 1

    return candidate


def _decimal(value):
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


@transaction.atomic
def _crear_real_desde_produccion_movil(cleaned, user):
    tarea = cleaned["tarea_obra"]
    fecha = cleaned["fecha"]
    modo = cleaned["modo"]
    empleado = cleaned.get("empleado")
    recurso = cleaned.get("recurso")
    cantidad = cleaned.get("cantidad") or Decimal("0")
    precio = cleaned.get("precio_unidad")
    unidad = cleaned.get("unidad") or ""
    observaciones = cleaned.get("observaciones") or ""

    team = tarea.team
    precio = _decimal(precio)
    coste = (cantidad * precio).quantize(Decimal("0.0001"))

    obj = TareaRecursoReal(
        team=team,
        legacy_id_recurso_tarea=_next_mobile_legacy_id(team),
        tarea_obra=tarea,
        unidad_obra=tarea.unidad_obra,
        partida=tarea.partida,
        recurso=None,
        empleado=None,
        legacy_cod_obra=tarea.legacy_cod_obra,
        legacy_cod_fase=tarea.legacy_cod_fase,
        legacy_cod_vivienda=tarea.legacy_cod_vivienda or "",
        legacy_planta=tarea.legacy_planta or "",
        legacy_capitulo=tarea.legacy_capitulo or _codigo(tarea.capitulo),
        legacy_partida=tarea.legacy_partida or _codigo(tarea.partida),
        legacy_id_movimiento_almacen=None,
        legacy_orden_recurso=None,
        unidad=unidad,
        cantidad=cantidad,
        precio_unidad=precio,
        dias=Decimal("0.0000"),
        dias_reales=Decimal("1.0000"),
        inicio_recurso_real=fecha,
        fin_recurso_real=fecha,
        costo_recurso=coste,
        costo_recurso_real=coste,
        control_suministros=False,
        avisar=0,
        observaciones=observaciones,
        raw_data={
            "origen": "obra_movil_produccion",
            "created_from": "obra_movil.produccion_nueva",
            "created_by_user_id": getattr(user, "id", None),
            "created_at": timezone.now().isoformat(),
            "mobile_phase": "fase2a",
            "legacy_id_policy": ">= 900000000 por team",
        },
    )

    if modo == ProduccionMovilForm.MODO_EMPLEADO:
        obj.empleado = empleado
        obj.recurso = None
        obj.legacy_id_recurso = empleado.legacy_id
        obj.legacy_tipo_recurso = _tipo_recurso_empleado(empleado)
        obj.legacy_personal = empleado.legacy_id
        obj.unidad = "HRS"
        obj.horas = cantidad
        obj.horas_reales = cantidad
    else:
        obj.recurso = recurso
        obj.empleado = None
        obj.legacy_id_recurso = recurso.legacy_id
        obj.legacy_tipo_recurso = recurso.tipo or ""
        obj.legacy_personal = None
        obj.horas = Decimal("0.0000")
        obj.horas_reales = Decimal("0.0000")

    obj.save()
    return obj


@login_required
def produccion_nueva(request):
    # OBRA_MOVIL_PRODUCCION_FILTERS_V1
    filtro_data = request.POST if request.method == "POST" else request.GET
    filtro_form = ProduccionMovilFiltroForm(request.GET or None, request=request)

    if request.method == "POST":
        form = ProduccionMovilForm(request.POST, request=request, filters=filtro_data)
        if form.is_valid():
            obj = _crear_real_desde_produccion_movil(form.cleaned_data, request.user)
            messages.success(
                request,
                f"Producción registrada correctamente. Real #{obj.pk} · {obj.cantidad} {obj.unidad}",
            )
            return redirect("obra_movil:produccion_home")
    else:
        form = ProduccionMovilForm(
            request=request,
            filters=request.GET,
            initial={"fecha": timezone.localdate()},
        )

    filtros_hidden = {
        key: filtro_data.get(key)
        for key in ["f_obra", "f_unidad_obra", "f_capitulo", "f_partida"]
        if filtro_data.get(key)
    }

    context = _dashboard_context(request)
    context.update({
        "page_title": "Nueva producción",
        "form": form,
        "filtro_form": filtro_form,
        "filtros_hidden": filtros_hidden,
        "tareas_disponibles_count": form.fields["tarea_obra"].queryset.count(),
        "tareas_limitadas": getattr(form, "tareas_limitadas", False),
    })
    return render(request, "obra_movil/produccion_form.html", context)



# OBRA_MOVIL_ALMACEN_CREATE_V1

def _next_legacy_id_movimiento():
    current = (
        RecursoAlmacenMovimiento.objects
        .aggregate(m=Max("legacy_id_movimiento"))
        .get("m")
    )
    candidate = (current or 0) + 1

    while RecursoAlmacenMovimiento.objects.filter(legacy_id_movimiento=candidate).exists():
        candidate += 1

    return candidate


def _q_stock(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.001"))


def _q_quedan(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.0001"))


@transaction.atomic
def _crear_movimiento_almacen_movil(cleaned, user):
    almacen = cleaned["almacen"]
    recurso_form = cleaned["recurso"]

    recurso = (
        RecursoCatalogo.objects
        .select_for_update()
        .get(pk=recurso_form.pk)
    )

    tipo = cleaned["tipo_movimiento"]
    cantidad = Decimal(str(cleaned["cantidad"] or 0))
    stock_actual = _q_stock(cleaned.get("_stock_operativo_almacen")) if cleaned.get("_stock_operativo_almacen") is not None else _alm_ux2e1_v7_stock_almacen_real(recurso, almacen)
    unidad = (
        str(
            recurso.unidad
            or cleaned.get("unidad")
            or ""
        )
        .strip()
    )

    # ALMACEN_RAPIDO_STOCK_NEGATIVO_V1
    stock_insuficiente = (
        tipo in ("SALIDA", "ROTURA")
        and stock_actual < cantidad
    )

    if tipo == "ENTRADA":
        nuevo_stock = _q_stock(stock_actual + cantidad)
    elif tipo in ("SALIDA", "ROTURA"):
        # Regla operativa INTASA:
        # la salida siempre se registra aunque el saldo quede negativo.
        nuevo_stock = _q_stock(stock_actual - cantidad)
    elif tipo == "CONTROL_STOCK":
        nuevo_stock = _q_stock(cantidad)
    else:
        nuevo_stock = stock_actual

    unidad_obra = cleaned.get("unidad_obra")
    partida = cleaned.get("partida")
    empleado = cleaned.get("empleado")
    fecha = cleaned.get("fecha_movimiento") or timezone.localdate() or timezone.localdate()
    hora = cleaned.get("hora_movimiento") or timezone.localtime().time()

    obra = almacen.obra

    mov = RecursoAlmacenMovimiento.objects.create(
        team=almacen.team,
        legacy_id_movimiento=_next_legacy_id_movimiento(),
        almacen=almacen,
        recurso=recurso,
        obra=obra,
        unidad_obra=unidad_obra,
        empleado=empleado,
        partida=partida,
        legacy_id_almacen=almacen.legacy_id_almacen or "",
        legacy_cod_recurso=recurso.legacy_id,
        legacy_cod_obra=getattr(obra, "legacy_cod_obra", None),
        legacy_cod_fase=getattr(unidad_obra, "legacy_cod_fase", None) if unidad_obra else None,
        legacy_cod_vivienda=(getattr(unidad_obra, "legacy_cod_vivienda", "") or "") if unidad_obra else "",
        legacy_planta="",
        legacy_capitulo=(getattr(getattr(partida, "capitulo", None), "codigo", "") or "") if partida else "",
        legacy_partida=(getattr(partida, "codigo", "") or "") if partida else "",
        legacy_cod_personal=getattr(empleado, "legacy_id", None) if empleado else None,
        unidad=unidad,
        cantidad=cantidad,
        quedan=_q_quedan(nuevo_stock),
        fecha_movimiento=fecha,
        hora_movimiento=hora,
        tipo_movimiento=tipo,
        tipo_movimiento_raw="CONTROL STOCK" if tipo == "CONTROL_STOCK" else tipo,
        en_partida=bool(partida),
        vehiculo=cleaned.get("vehiculo") or "",
        kilometraje=cleaned.get("kilometraje"),
        observaciones=cleaned.get("observaciones") or "",
        raw_data={
            "origen": "obra_movil_almacen",
            "created_from": "obra_movil.almacen_nuevo",
            "created_by_user_id": getattr(user, "id", None),
            "created_at": timezone.now().isoformat(),
            "mobile_phase": "fase3a",
            "stock_anterior": str(stock_actual),
            "stock_nuevo": str(nuevo_stock),
            "stock_policy": (
                "ENTRADA suma; SALIDA/ROTURA resta y permite "
                "saldo negativo con aviso; CONTROL_STOCK fija stock"
            ),
            "stock_insuficiente": bool(stock_insuficiente),
            "stock_negativo": bool(nuevo_stock < 0),
            "stock_faltante": (
                str(abs(nuevo_stock))
                if nuevo_stock < 0
                else "0"
            ),
            "stock_warning_marker": "ALMACEN_RAPIDO_STOCK_NEGATIVO_V1",
        },
    )

    recurso.stock = nuevo_stock
    recurso.control_stock = True
    recurso.save(update_fields=["stock", "control_stock", "actualizado_en"])

    return mov


@login_required
def almacen_nuevo(request):
    # OBRA_MOVIL_ALMACEN_FILTERS_V1
    filtro_data = request.POST if request.method == "POST" else request.GET
    filtro_form = AlmacenMovimientoFiltroForm(request.GET or None, request=request)

    if request.method == "POST":
        form = AlmacenMovimientoMovilForm(request.POST, request=request, filters=filtro_data)
        if form.is_valid():
            try:
                mov = _crear_movimiento_almacen_movil(form.cleaned_data, request.user)
            except ValueError as exc:
                form.add_error("cantidad", str(exc))
            else:
                messages.success(
                    request,
                    f"Movimiento de almacén registrado. #{mov.legacy_id_movimiento} · {mov.tipo_movimiento} · quedan {mov.quedan} {mov.unidad}",
                )
                return redirect("obra_movil:almacen_home")
    else:
        initial = {
            "fecha_movimiento": timezone.localdate(),
            "hora_movimiento": timezone.localtime().strftime("%H:%M"),
        }

        if request.GET.get("f_almacen"):
            initial["almacen"] = request.GET.get("f_almacen")

        if request.GET.get("tipo"):
            initial["tipo_movimiento"] = request.GET.get("tipo")

        form = AlmacenMovimientoMovilForm(
            request=request,
            filters=request.GET,
            initial=initial,
        )

    filtros_hidden = {
        key: filtro_data.get(key)
        for key in ["f_almacen", "q_recurso"]
        if filtro_data.get(key)
    }

    context = _dashboard_context(request)
    context.update({
        "page_title": "Nuevo movimiento de almacén",
        "form": form,
        "filtro_form": filtro_form,
        "filtros_hidden": filtros_hidden,
        "recursos_disponibles_count": form.fields["recurso"].queryset.count(),
        "recursos_limitados": getattr(form, "recursos_limitados", False),
    })
    return render(request, "obra_movil/almacen_form.html", context)


@login_required
def almacen_home(request):
    return _section(
        request,
        "almacen",
        "Almacén",
        "Movimientos móviles de entrada, salida, rotura y control de stock.",
        "bi-box-seam",
        reverse("obra_movil:almacen_rapido"),
    )



# OBRA_MOVIL_MORTERO_GASOIL_SHORTCUTS_V1

def _find_almacen_like(words):
    qs = AlmacenObra.objects.select_related("team", "obra").all()
    for word in words:
        qs = qs.filter(nombre__icontains=word)
    return qs.order_by("id").first()


def _find_recurso_like(words):
    qs = RecursoCatalogo.objects.filter(control_stock=True)
    for word in words:
        qs = qs.filter(nombre__icontains=word)
    return qs.order_by("id").first()


@login_required
def mortero_nuevo(request):
    almacen = (
        _find_almacen_like(["MORTERO"])
        or _find_almacen_like(["SILO"])
    )
    recurso = (
        _find_recurso_like(["MORTERO"])
        or _find_recurso_like(["CUBAS"])
    )

    q = {}
    if almacen:
        q["f_almacen"] = str(almacen.pk)
    if recurso:
        q["q_recurso"] = str(recurso.legacy_id or recurso.nombre)
    q["tipo"] = "SALIDA"

    from urllib.parse import urlencode
    return redirect(f"{reverse('obra_movil:almacen_nuevo')}?{urlencode(q)}")


@login_required
def gasoil_nuevo(request):
    almacen = (
        _find_almacen_like(["GASOLEO"])
        or _find_almacen_like(["GASOIL"])
        or _find_almacen_like(["DEPOSITO"])
    )
    recurso = (
        _find_recurso_like(["GASOLEO"])
        or _find_recurso_like(["GASOIL"])
    )

    q = {}
    if almacen:
        q["f_almacen"] = str(almacen.pk)
    if recurso:
        q["q_recurso"] = str(recurso.legacy_id or recurso.nombre)
    q["tipo"] = "SALIDA"

    from urllib.parse import urlencode
    return redirect(f"{reverse('obra_movil:almacen_nuevo')}?{urlencode(q)}")


# OBRA_MOVIL_STOCK_LIST_V1

def _stock_scoped(qs, request):
    return filter_by_active_team(qs, request)



# OBRA_MOVIL_ALMACEN_RAPIDO_VIEW_V1

@login_required
def almacen_rapido(request):
    # GAS_UX1C_ALMACEN_RAPIDO_REDIRECT_OK
    gas_q = (
        request.GET.get("q_recurso")
        or request.GET.get("q")
        or request.GET.get("recurso")
        or ""
    ).strip().upper()
    if request.method == "GET" and gas_q in {"167", "GASOIL", "GAS-OIL"}:
        return redirect("obra_movil:gasoil_salida_vehiculo")

    if request.method == "POST":
        form = AlmacenRapidoForm(request.POST, request=request)
        if form.is_valid():
            mov = _crear_movimiento_almacen_movil(form.cleaned_data, request.user)
            _alm_ux2e1_sync_movimiento_a_planificacion(mov, request=request)


            destino = form.cleaned_data.get("destino") or "ALMACEN"
            en_partida = destino == "PARTIDA" and bool(mov.partida_id)

            raw = mov.raw_data if isinstance(mov.raw_data, dict) else {}
            raw.update({
                "ui": "almacen_rapido",
                "destino_operativo": destino,
                "mobile_phase": "alm_ux1a",
            })

            mov.en_partida = en_partida
            mov.raw_data = raw
            mov.save(update_fields=["en_partida", "raw_data"])

            if destino == "PERSONA":
                destino_msg = f"entregado a {mov.empleado}"
            elif destino == "PARTIDA":
                destino_msg = "imputado a vivienda/partida"
            else:
                destino_msg = "registrado en almacén"

            # ALMACEN_RAPIDO_STOCK_NEGATIVO_V1
            if raw.get("stock_insuficiente"):
                messages.warning(
                    request,
                    (
                        "Aviso de stock: el movimiento SE HA GUARDADO "
                        "aunque no había existencias suficientes. "
                        f"Stock anterior: {raw.get('stock_anterior', '—')} "
                        f"{mov.unidad}. "
                        f"Stock resultante: {mov.quedan} {mov.unidad}."
                    ),
                )

            messages.success(
                request,
                f"{mov.tipo_movimiento} registrado. #{mov.legacy_id_movimiento} · {destino_msg} · quedan {mov.quedan} {mov.unidad}",
            )

            from urllib.parse import urlencode
            params = {
                "almacen": mov.almacen_id,
                "tipo_recurso": form.cleaned_data.get("tipo_recurso") or "",
                "q_recurso": mov.recurso.legacy_id if mov.recurso_id else "",
            }
            return redirect(f"{reverse('obra_movil:almacen_rapido')}?{urlencode(params)}")
    else:
        # ALMACEN_RAPIDO_GET_UNBOUND_FIX_V1
        #
        # Los parámetros GET son únicamente valores de precarga/filtro.
        # Nunca deben enlazar (bind) AlmacenRapidoForm, porque después de
        # un POST correcto el redirect contiene ?almacen=...&tipo_recurso=...
        # &q_recurso=... y Django interpretaba ese GET incompleto como un
        # formulario enviado, mostrando falsos errores "NO se ha guardado".
        initial = {
            "fecha_movimiento": timezone.localdate(),
            "hora_movimiento": timezone.localtime().strftime("%H:%M"),
            "tipo_movimiento": request.GET.get("tipo_movimiento") or "SALIDA",
            "destino": request.GET.get("destino") or "PARTIDA",
            "tipo_recurso": request.GET.get("tipo_recurso") or "",
            "q_recurso": (
                request.GET.get("q_recurso")
                or request.GET.get("q")
                or ""
            ),
            "almacen": request.GET.get("almacen") or None,
        }

        # Permitir precarga explícita de recurso cuando alguna entrada
        # legítima llegue con ?recurso=<pk>, pero siempre como initial.
        if request.GET.get("recurso"):
            initial["recurso"] = request.GET.get("recurso")

        form = AlmacenRapidoForm(
            request=request,
            initial=initial,
        )

    context = _dashboard_context(request)
    context.update({
        "page_title": "Almacén rápido",
        "form": form,
        "recursos_disponibles_count": getattr(form, "recursos_disponibles_count", 0),
    })
    return render(request, "obra_movil/almacen_rapido.html", context)


@login_required
def stock_home(request):
    filtro_form = StockMovilFiltroForm(request.GET or None, request=request)

    recursos_qs = _stock_scoped(
        RecursoCatalogo.objects.select_related("team", "capitulo").filter(control_stock=True),
        request,
    )

    q = (request.GET.get("q") or "").strip()
    tipo = request.GET.get("tipo") or ""
    almacen_id = request.GET.get("almacen") or ""

    if q:
        filtro = Q(nombre__icontains=q)
        if q.isdigit():
            filtro |= Q(legacy_id=int(q))
        recursos_qs = recursos_qs.filter(filtro)

    if tipo:
        recursos_qs = recursos_qs.filter(tipo=tipo)

    total_filtrado = recursos_qs.count()

    recursos = list(
        recursos_qs
        .order_by("tipo", "nombre", "legacy_id", "id")[:120]
    )

    recurso_ids = [r.id for r in recursos]

    movs = (
        RecursoAlmacenMovimiento.objects
        .select_related("almacen", "obra", "unidad_obra", "partida", "empleado")
        .filter(recurso_id__in=recurso_ids)
        .order_by("-id")
    )

    if almacen_id:
        movs = movs.filter(almacen_id=almacen_id)

    ultimo_por_recurso = {}
    for mov in movs[:800]:
        if mov.recurso_id not in ultimo_por_recurso:
            ultimo_por_recurso[mov.recurso_id] = mov

    rows = []
    for r in recursos:
        mov = ultimo_por_recurso.get(r.id)
        rows.append({
            "recurso": r,
            "ultimo_movimiento": mov,
        })

    context = _dashboard_context(request)
    context.update({
        "page_title": "Stock móvil",
        "filtro_form": filtro_form,
        "rows": rows,
        "total_filtrado": total_filtrado,
        "limit": 120,
        "q": q,
        "tipo": tipo,
        "almacen_id": almacen_id,
    })
    return render(request, "obra_movil/stock_list.html", context)


# OBRA_MOVIL_STOCK_CONTROL_V1

@transaction.atomic
def _crear_control_stock_movil(cleaned, user):
    almacen = cleaned["almacen"]
    recurso_form = cleaned["recurso"]

    recurso = (
        RecursoCatalogo.objects
        .select_for_update()
        .get(pk=recurso_form.pk)
    )

    stock_anterior = _q_stock(recurso.stock)
    stock_nuevo = _q_stock(cleaned["stock_contado"])
    unidad = (
        str(
            recurso.unidad
            or cleaned.get("unidad")
            or ""
        )
        .strip()
    )
    fecha = cleaned.get("fecha_movimiento")
    hora = cleaned.get("hora_movimiento") or timezone.localtime().time()

    if recurso.team_id != almacen.team_id:
        raise ValueError("El recurso no pertenece a la misma empresa que el almacén.")

    mov = RecursoAlmacenMovimiento.objects.create(
        team=almacen.team,
        legacy_id_movimiento=_next_legacy_id_movimiento(),
        almacen=almacen,
        recurso=recurso,
        obra=almacen.obra,
        unidad_obra=None,
        empleado=None,
        partida=None,
        legacy_id_almacen=almacen.legacy_id_almacen or "",
        legacy_cod_recurso=recurso.legacy_id,
        legacy_cod_obra=getattr(almacen.obra, "legacy_cod_obra", None),
        legacy_cod_fase=None,
        legacy_cod_vivienda="",
        legacy_planta="",
        legacy_capitulo="",
        legacy_partida="",
        legacy_cod_personal=None,
        unidad=unidad,
        cantidad=stock_nuevo,
        quedan=_q_quedan(stock_nuevo),
        fecha_movimiento=fecha,
        hora_movimiento=hora,
        tipo_movimiento="CONTROL_STOCK",
        tipo_movimiento_raw="CONTROL STOCK",
        en_partida=False,
        vehiculo="",
        kilometraje=None,
        observaciones=cleaned.get("observaciones") or "",
        raw_data={
            "origen": "obra_movil_control_stock",
            "created_from": "obra_movil.stock_control",
            "created_by_user_id": getattr(user, "id", None),
            "created_at": timezone.now().isoformat(),
            "mobile_phase": "fase4b",
            "stock_anterior": str(stock_anterior),
            "stock_nuevo": str(stock_nuevo),
            "stock_policy": "CONTROL_STOCK fija stock al conteo real",
        },
    )

    recurso.stock = stock_nuevo
    recurso.control_stock = True
    recurso.save(update_fields=["stock", "control_stock", "actualizado_en"])

    return mov


@login_required
def stock_control(request, recurso_pk=None):
    if request.method == "POST":
        form = ControlStockMovilForm(request.POST, request=request, recurso_pk=recurso_pk)
        if form.is_valid():
            try:
                mov = _crear_control_stock_movil(form.cleaned_data, request.user)
            except ValueError as exc:
                form.add_error("recurso", str(exc))
            else:
                messages.success(
                    request,
                    f"Control de stock registrado. #{mov.legacy_id_movimiento} · quedan {mov.quedan} {mov.unidad}",
                )
                return redirect("obra_movil:stock_home")
    else:
        form = ControlStockMovilForm(
            request=request,
            recurso_pk=recurso_pk,
            initial={
                "fecha_movimiento": timezone.localdate(),
                "hora_movimiento": timezone.localtime().strftime("%H:%M"),
            },
        )

    context = _dashboard_context(request)
    context.update({
        "page_title": "Control de stock",
        "form": form,
        "recurso_pk": recurso_pk,
    })
    return render(request, "obra_movil/stock_control_form.html", context)


@login_required
def mortero_home(request):
    return _section(
        request,
        "mortero",
        "Mortero",
        "Movimientos de cubas, entradas, salidas y quedan. Fase 4.",
        "bi-bricks",
    )


@login_required
def gasoil_home(request):
    return _section(
        request,
        "gasoil",
        "Gasoil",
        "Control de consumos, vehículos y kilometraje. Fase 4.",
        "bi-fuel-pump",
    )



# OBRA_MOVIL_HISTORIAL_V1
# OBRA_MOVIL_HISTORIAL_DETAIL_URLS_V1

def _hist_dt(obj):
    return (
        getattr(obj, "created_at", None)
        or getattr(obj, "updated_at", None)
        or timezone.now()
    )


def _hist_str(value, default="-"):
    if value in (None, ""):
        return default
    return str(value)


# OBRA_MOVIL_HISTORIAL_SCOPE_V2
def _mobile_scope_for_history(qs, request):
    """
    Scope móvil seguro:
    - Si hay empresa activa explícita, filtra por esa empresa.
    - Si active_team_id es "all" o no existe, superuser ve todo.
    - Usuario normal ve solo sus teams.
    """
    user = getattr(request, "user", None)
    active_team_id = None

    try:
        active_team_id = request.session.get("active_team_id")
    except Exception:
        active_team_id = None

    if active_team_id not in (None, "", "all"):
        active_team = get_active_team(request)
        if active_team is not None:
            return qs.filter(team=active_team)

    if user is not None and not getattr(user, "is_superuser", False) and hasattr(user, "teams"):
        return qs.filter(team__in=user.teams.all())

    return qs


@login_required
def historial_home(request):
    tipo = request.GET.get("tipo") or ""
    q = (request.GET.get("q") or "").strip()

    producciones_qs = _mobile_scope_for_history(
        TareaRecursoReal.objects.select_related(
            "team",
            "tarea_obra",
            "tarea_obra__obra",
            "unidad_obra",
            "partida",
            "recurso",
            "empleado",
        ).filter(raw_data__origen="obra_movil_produccion"),
        request,
    )

    movimientos_qs = _mobile_scope_for_history(
        RecursoAlmacenMovimiento.objects.select_related(
            "team",
            "almacen",
            "obra",
            "unidad_obra",
            "partida",
            "recurso",
            "empleado",
        ).filter(raw_data__origen__in=["obra_movil_almacen", "obra_movil_control_stock"]),
        request,
    )

    if tipo == "produccion":
        movimientos_qs = movimientos_qs.none()
    elif tipo == "almacen":
        producciones_qs = producciones_qs.none()
        movimientos_qs = movimientos_qs.filter(raw_data__origen="obra_movil_almacen")
    elif tipo == "control_stock":
        producciones_qs = producciones_qs.none()
        movimientos_qs = movimientos_qs.filter(raw_data__origen="obra_movil_control_stock")

    if q:
        prod_filter = (
            Q(observaciones__icontains=q)
            | Q(recurso__nombre__icontains=q)
            | Q(empleado__nombre__icontains=q)
        )
        mov_filter = (
            Q(observaciones__icontains=q)
            | Q(recurso__nombre__icontains=q)
            | Q(almacen__nombre__icontains=q)
            | Q(tipo_movimiento__icontains=q)
        )

        if q.isdigit():
            prod_filter |= Q(legacy_id_recurso_tarea=int(q)) | Q(legacy_id_recurso=int(q))
            mov_filter |= Q(legacy_id_movimiento=int(q)) | Q(legacy_cod_recurso=int(q))

        producciones_qs = producciones_qs.filter(prod_filter)
        movimientos_qs = movimientos_qs.filter(mov_filter)

    producciones_count = producciones_qs.count()
    movimientos_count = movimientos_qs.count()

    rows = []

    for obj in producciones_qs.order_by("-id")[:80]:
        tarea = getattr(obj, "tarea_obra", None)
        obra = getattr(tarea, "obra", None) if tarea else None
        subject = obj.empleado or obj.recurso
        rows.append({
            "detail_url": reverse("obra_movil:historial_produccion_detail", args=[obj.pk]),
            "kind": "produccion",
            "kind_label": "Producción",
            "badge_class": "bg-success-subtle text-success-emphasis",
            "dt": _hist_dt(obj),
            "title": _hist_str(subject, "Producción real"),
            "subtitle": " · ".join(x for x in [
                _hist_str(obra, ""),
                _hist_str(obj.unidad_obra, ""),
                _hist_str(obj.partida, ""),
            ] if x),
            "amount": f"{obj.cantidad or 0} {obj.unidad or ''}".strip(),
            "detail": obj.observaciones or "",
            "legacy": obj.legacy_id_recurso_tarea,
            "stock_or_quedan": "",
        })

    for obj in movimientos_qs.order_by("-id")[:80]:
        origin = obj.raw_data.get("origen") if isinstance(obj.raw_data, dict) else ""
        is_control = origin == "obra_movil_control_stock"
        rows.append({
            "detail_url": reverse("obra_movil:historial_movimiento_detail", args=[obj.pk]),
            "kind": "control_stock" if is_control else "almacen",
            "kind_label": "Control stock" if is_control else "Almacén",
            "badge_class": "bg-warning-subtle text-warning-emphasis" if is_control else "bg-primary-subtle text-primary-emphasis",
            "dt": _hist_dt(obj),
            "title": _hist_str(obj.recurso, "Movimiento de almacén"),
            "subtitle": " · ".join(x for x in [
                _hist_str(obj.almacen, ""),
                _hist_str(obj.unidad_obra, ""),
                _hist_str(obj.partida, ""),
                _hist_str(obj.empleado, ""),
            ] if x),
            "amount": f"{obj.tipo_movimiento} · {obj.cantidad or 0} {obj.unidad or ''}".strip(),
            "detail": obj.observaciones or "",
            "legacy": obj.legacy_id_movimiento,
            "stock_or_quedan": f"Quedan {obj.quedan}" if obj.quedan is not None else "",
        })

    rows = sorted(rows, key=lambda row: row["dt"], reverse=True)[:80]

    tipo_choices = [
        ("", "Todo"),
        ("produccion", "Producción"),
        ("almacen", "Almacén"),
        ("control_stock", "Control stock"),
    ]

    context = _dashboard_context(request)
    context.update({
        "page_title": "Historial móvil",
        "rows": rows,
        "tipo": tipo,
        "q": q,
        "tipo_choices": tipo_choices,
        "producciones_count": producciones_count,
        "movimientos_count": movimientos_count,
        "total_count": producciones_count + movimientos_count,
        "limit": 80,
    })
    return render(request, "obra_movil/historial.html", context)



# OBRA_MOVIL_HISTORIAL_DETAIL_V1

def _raw_items(raw_data):
    if not isinstance(raw_data, dict):
        return []
    return [
        {"key": str(k), "value": _hist_str(v)}
        for k, v in sorted(raw_data.items(), key=lambda item: str(item[0]))
    ]


def _detail_item(label, value):
    return {
        "label": label,
        "value": _hist_str(value),
    }


@login_required
def historial_produccion_detail(request, pk):
    obj = (
        _mobile_scope_for_history(
            TareaRecursoReal.objects.select_related(
                "team",
                "tarea_obra",
                "tarea_obra__obra",
                "unidad_obra",
                "partida",
                "recurso",
                "empleado",
            ).filter(raw_data__origen="obra_movil_produccion"),
            request,
        )
        .filter(pk=pk)
        .first()
    )

    if not obj:
        raise Http404("Producción móvil no encontrada")

    tarea = obj.tarea_obra
    obra = getattr(tarea, "obra", None) if tarea else None

    items = [
        _detail_item("ID interno", obj.pk),
        _detail_item("Legacy móvil", obj.legacy_id_recurso_tarea),
        _detail_item("Empresa", obj.team),
        _detail_item("Obra", obra),
        _detail_item("Tarea", tarea),
        _detail_item("Unidad obra", obj.unidad_obra),
        _detail_item("Partida", obj.partida),
        _detail_item("Empleado", obj.empleado),
        _detail_item("Recurso", obj.recurso),
        _detail_item("Cantidad", obj.cantidad),
        _detail_item("Unidad", obj.unidad),
        _detail_item("Precio unidad", obj.precio_unidad),
        _detail_item("Coste real", obj.costo_recurso_real),
        _detail_item("Horas reales", obj.horas_reales),
        _detail_item("Fecha inicio", obj.inicio_recurso_real),
        _detail_item("Fecha fin", obj.fin_recurso_real),
        _detail_item("Observaciones", obj.observaciones),
    ]

    actions = [
        {
            "label": "Volver al historial",
            "url": reverse("obra_movil:historial_home"),
            "class": "btn-light",
            "icon": "bi-clock-history",
        },
        {
            "label": "Nueva producción",
            "url": reverse("obra_movil:produccion_nueva"),
            "class": "btn-primary",
            "icon": "bi-person-check",
        },
    ]

    if obj.recurso_id:
        actions.append({
            "label": "Ver stock recurso",
            "url": f"{reverse('obra_movil:stock_home')}?q={obj.recurso.legacy_id}",
            "class": "btn-outline-primary",
            "icon": "bi-clipboard-data",
        })

    context = _dashboard_context(request)
    context.update({
        "page_title": "Detalle producción móvil",
        "detail_marker": "OBRA_MOVIL_HISTORIAL_PRODUCCION_DETAIL_V1",
        "title": "Detalle producción",
        "badge": "Producción",
        "badge_class": "bg-success-subtle text-success-emphasis",
        "subtitle": f"#{obj.legacy_id_recurso_tarea}",
        "items": items,
        "raw_items": _raw_items(obj.raw_data),
        "actions": actions,
    })
    return render(request, "obra_movil/historial_detail.html", context)


@login_required
def historial_movimiento_detail(request, pk):
    obj = (
        _mobile_scope_for_history(
            RecursoAlmacenMovimiento.objects.select_related(
                "team",
                "almacen",
                "obra",
                "unidad_obra",
                "partida",
                "recurso",
                "empleado",
            ).filter(raw_data__origen__in=["obra_movil_almacen", "obra_movil_control_stock"]),
            request,
        )
        .filter(pk=pk)
        .first()
    )

    if not obj:
        raise Http404("Movimiento móvil no encontrado")

    origin = obj.raw_data.get("origen") if isinstance(obj.raw_data, dict) else ""
    is_control = origin == "obra_movil_control_stock"

    items = [
        _detail_item("ID interno", obj.pk),
        _detail_item("Legacy movimiento", obj.legacy_id_movimiento),
        _detail_item("Empresa", obj.team),
        _detail_item("Tipo", obj.tipo_movimiento),
        _detail_item("Almacén", obj.almacen),
        _detail_item("Obra", obj.obra),
        _detail_item("Unidad obra", obj.unidad_obra),
        _detail_item("Partida", obj.partida),
        _detail_item("Empleado", obj.empleado),
        _detail_item("Recurso", obj.recurso),
        _detail_item("Cantidad", obj.cantidad),
        _detail_item("Quedan", obj.quedan),
        _detail_item("Unidad", obj.unidad),
        _detail_item("Fecha", obj.fecha_movimiento),
        _detail_item("Hora", obj.hora_movimiento),
        _detail_item("Vehículo", obj.vehiculo),
        _detail_item("Kilometraje", obj.kilometraje),
        _detail_item("Observaciones", obj.observaciones),
    ]

    actions = [
        {
            "label": "Volver al historial",
            "url": reverse("obra_movil:historial_home"),
            "class": "btn-light",
            "icon": "bi-clock-history",
        },
        {
            "label": "Movimiento almacén",
            "url": reverse("obra_movil:almacen_nuevo"),
            "class": "btn-primary",
            "icon": "bi-box-seam",
        },
    ]

    if obj.recurso_id:
        actions.append({
            "label": "Controlar stock",
            "url": reverse("obra_movil:stock_control_recurso", args=[obj.recurso_id]),
            "class": "btn-outline-primary",
            "icon": "bi-clipboard-check",
        })
        actions.append({
            "label": "Ver stock recurso",
            "url": f"{reverse('obra_movil:stock_home')}?q={obj.recurso.legacy_id}",
            "class": "btn-outline-secondary",
            "icon": "bi-clipboard-data",
        })

    context = _dashboard_context(request)
    context.update({
        "page_title": "Detalle movimiento móvil",
        "detail_marker": "OBRA_MOVIL_HISTORIAL_MOVIMIENTO_DETAIL_V1",
        "title": "Detalle control stock" if is_control else "Detalle movimiento",
        "badge": "Control stock" if is_control else "Almacén",
        "badge_class": "bg-warning-subtle text-warning-emphasis" if is_control else "bg-primary-subtle text-primary-emphasis",
        "subtitle": f"#{obj.legacy_id_movimiento}",
        "items": items,
        "raw_items": _raw_items(obj.raw_data),
        "actions": actions,
    })
    return render(request, "obra_movil/historial_detail.html", context)


# OBRA_MOVIL_INCIDENCIAS_V1

def _incidencias_scope(qs, request):
    user = getattr(request, "user", None)
    active_team_id = None

    try:
        active_team_id = request.session.get("active_team_id")
    except Exception:
        active_team_id = None

    if active_team_id not in (None, "", "all"):
        active_team = get_active_team(request)
        if active_team is not None:
            return qs.filter(team=active_team)

    if user is not None and not getattr(user, "is_superuser", False) and hasattr(user, "teams"):
        return qs.filter(team__in=user.teams.all())

    return qs


@login_required
def incidencias_home(request):
    filtro_form = IncidenciaMovilFiltroForm(request.GET or None)

    qs = _incidencias_scope(
        IncidenciaObraMovil.objects.select_related(
            "team",
            "obra",
            "unidad_obra",
            "tarea_obra",
            "empleado",
            "created_by",
        ),
        request,
    )

    estado = request.GET.get("estado") or ""
    prioridad = request.GET.get("prioridad") or ""
    q = (request.GET.get("q") or "").strip()

    if estado:
        qs = qs.filter(estado=estado)

    if prioridad:
        qs = qs.filter(prioridad=prioridad)

    if q:
        filtro = (
            Q(titulo__icontains=q)
            | Q(descripcion__icontains=q)
            | Q(resolucion__icontains=q)
            | Q(obra__nombre__icontains=q)
            | Q(unidad_obra__edificio__icontains=q)
            | Q(unidad_obra__vivienda__icontains=q)
            | Q(empleado__nombre__icontains=q)
        )
        if q.isdigit():
            filtro |= Q(pk=int(q))
        qs = qs.filter(filtro)

    total_count = qs.count()
    abiertas_count = _incidencias_scope(
        IncidenciaObraMovil.objects.filter(estado__in=[
            IncidenciaObraMovil.Estado.ABIERTA,
            IncidenciaObraMovil.Estado.EN_CURSO,
        ]),
        request,
    ).count()

    rows = list(qs.order_by("-fecha", "-id")[:120])

    context = _dashboard_context(request)
    context.update({
        "page_title": "Incidencias",
        "filtro_form": filtro_form,
        "rows": rows,
        "total_count": total_count,
        "abiertas_count": abiertas_count,
        "limit": 120,
        "estado": estado,
        "prioridad": prioridad,
        "q": q,
    })
    return render(request, "obra_movil/incidencias_list.html", context)


@login_required
def incidencia_nueva(request):
    if request.method == "POST":
        form = IncidenciaObraMovilForm(request.POST, request=request)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.team = obj.obra.team
            obj.created_by = request.user
            obj.raw_data = {
                "origen": "obra_movil_incidencia",
                "created_from": "obra_movil.incidencia_nueva",
                "created_by_user_id": getattr(request.user, "id", None),
                "mobile_phase": "fase6b",
                "created_at": timezone.now().isoformat(),
            }

            if obj.estado == IncidenciaObraMovil.Estado.CERRADA:
                obj.closed_by = request.user
                obj.closed_at = timezone.now()

            obj.save()

            if obj.tarea_obra_id:
                obj.tarea_obra.con_incidencias = True
                obj.tarea_obra.save(update_fields=["con_incidencias"])

            messages.success(request, f"Incidencia creada correctamente. #{obj.pk}")
            return redirect("obra_movil:incidencia_detail", pk=obj.pk)
    else:
        form = IncidenciaObraMovilForm(
            request=request,
            initial={
                "fecha": timezone.localdate(),
                "estado": IncidenciaObraMovil.Estado.ABIERTA,
                "prioridad": IncidenciaObraMovil.Prioridad.MEDIA,
            },
        )

    context = _dashboard_context(request)
    context.update({
        "page_title": "Nueva incidencia",
        "form": form,
    })
    return render(request, "obra_movil/incidencia_form.html", context)


@login_required
def incidencia_detail(request, pk):
    obj = (
        _incidencias_scope(
            IncidenciaObraMovil.objects.select_related(
                "team",
                "obra",
                "unidad_obra",
                "tarea_obra",
                "empleado",
                "created_by",
                "closed_by",
            ),
            request,
        )
        .filter(pk=pk)
        .first()
    )

    if not obj:
        raise Http404("Incidencia no encontrada")

    raw_items = []
    if isinstance(obj.raw_data, dict):
        raw_items = [
            {"key": str(k), "value": str(v)}
            for k, v in sorted(obj.raw_data.items(), key=lambda item: str(item[0]))
        ]

    context = _dashboard_context(request)
    context.update({
        "page_title": "Detalle incidencia",
        "incidencia": obj,
        "raw_items": raw_items,
    })
    return render(request, "obra_movil/incidencia_detail.html", context)


# OBRA_MOVIL_ALM_UX1D_API_OK
# Endpoint ligero para autocompletar artículos desde Almacén rápido.
# Mantiene el flujo anterior sin JavaScript: usa la propia vista almacen_rapido para obtener opciones reales.
try:
    from django.http import JsonResponse
    from django.contrib.auth.decorators import login_required
    from django.views.decorators.http import require_GET
except Exception:
    pass

def _alm_ux1d_parse_recurso_options(html):
    import html as _html
    import re as _re
    from html.parser import HTMLParser

    class _Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_select = False
            self.target_select = False
            self.in_option = False
            self.current_value = ""
            self.current_text = ""
            self.options = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            tag = tag.lower()

            if tag == "select":
                name = attrs.get("name", "")
                self.in_select = True
                self.target_select = name == "recurso"

            if tag == "option" and self.in_select and self.target_select:
                self.in_option = True
                self.current_value = attrs.get("value", "")
                self.current_text = ""

        def handle_data(self, data):
            if self.in_option:
                self.current_text += data

        def handle_endtag(self, tag):
            tag = tag.lower()

            if tag == "option" and self.in_option:
                value = str(self.current_value or "").strip()
                text = _re.sub(r"\s+", " ", self.current_text or "").strip()
                if value:
                    self.options.append({"id": value, "text": _html.unescape(text)})
                self.in_option = False
                self.current_value = ""
                self.current_text = ""

            if tag == "select":
                self.in_select = False
                self.target_select = False

    parser = _Parser()
    parser.feed(html or "")
    return parser.options

def _alm_ux1d_parse_article_text(text):
    import re
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    parts = [p.strip() for p in clean.split(" - ") if p.strip()]

    codigo = ""
    nombre = clean

    if len(parts) >= 2 and len(parts[0]) <= 40:
        codigo = parts[0]
        nombre = " - ".join(parts[1:])

    unidad = ""
    tipo = ""

    m_unit = re.search(r"\b(UD|UND|UNIDAD|M|ML|M2|M3|KG|L|ROLLO|CAJA|SACO|PORTE|H|DIA|DÍA)\b", clean, re.I)
    if m_unit:
        unidad = m_unit.group(1).upper()

    m_tipo = re.search(r"\b(MATERIAL|MAQUINARIA|HERRAMIENTA|E\.?P\.?I\.?S?|EPIS|EPI)\b", clean, re.I)
    if m_tipo:
        tipo = m_tipo.group(1).upper().replace(".", "")

    return {
        "codigo": codigo,
        "nombre": nombre,
        "tipo": tipo,
        "unidad": unidad,
    }

def _alm_ux1d_format_number(value):
    try:
        dec = float(value or 0)
        if abs(dec - int(dec)) < 0.000001:
            return str(int(dec))
        return str(round(dec, 3)).rstrip("0").rstrip(".")
    except Exception:
        return str(value or "")


# OBRA_MOVIL_ALM_UX2B2_ORIGEN_CLARO_OK
def _alm_ux2b2_clean_display(value, fallback=""):
    text = str(value or "").strip()
    if not text or text.lower() in {"none", "null", "nan", "-"}:
        return fallback
    return text

def _alm_ux2b2_almacen_display(almacen_obj):
    # OBRA_MOVIL_ALM_UX2B3_ALMACEN_LABEL_REAL_OK
    def _clean(value):
        text = str(value or "").strip()
        if not text:
            return ""
        if text.lower() in {"none", "null", "nan", "-", "—"}:
            return ""
        if " object (" in text.lower():
            return ""
        return text

    def _first_attr(obj, names):
        for name in names:
            try:
                value = getattr(obj, name, None)
            except Exception:
                value = None
            value = _clean(value)
            if value:
                return value
        return ""

    def _first_text_field(obj, skip=()):
        try:
            fields = obj._meta.fields
        except Exception:
            return ""

        skip = set(skip or ())

        for field in fields:
            name = getattr(field, "name", "")
            if name in skip:
                continue

            try:
                value = getattr(obj, name, None)
            except Exception:
                continue

            value = _clean(value)

            if value and len(value) <= 80:
                return value

        return ""

    obra_obj = getattr(almacen_obj, "obra", None)

    obra_nombre = ""
    if obra_obj is not None:
        obra_nombre = (
            _first_attr(obra_obj, [
                "nombre", "name", "descripcion", "denominacion",
                "obra", "codigo", "cod_obra", "legacy_cod_obra"
            ])
            or _clean(str(obra_obj))
        )

    almacen_nombre = (
        _first_attr(almacen_obj, [
            "nombre", "name", "descripcion", "denominacion",
            "almacen", "codigo", "cod_almacen", "legacy_id_almacen"
        ])
        or _first_text_field(almacen_obj, skip=("id", "team", "obra"))
        or _clean(str(almacen_obj))
    )

    raw = _clean(str(almacen_obj))

    # Si los campos vienen vacíos pero __str__ trae algo útil, úsalo.
    if raw and (not obra_nombre or not almacen_nombre):
        for sep in [" · ", " - ", " / ", " | "]:
            if sep in raw:
                parts = [p.strip() for p in raw.split(sep) if _clean(p)]
                if len(parts) >= 2:
                    if not obra_nombre:
                        obra_nombre = parts[0]
                    if not almacen_nombre:
                        almacen_nombre = sep.join(parts[1:])
                    break

        if not almacen_nombre:
            almacen_nombre = raw

    obra_nombre = _clean(obra_nombre)
    almacen_nombre = _clean(almacen_nombre)

    if not almacen_nombre:
        almacen_nombre = "SIN ALMACÉN"

    # Si no hay obra ni nombre real, no mostrar “Almacén” genérico.
    if almacen_nombre.strip().lower() in {"almacén", "almacen"} and not obra_nombre:
        almacen_nombre = "SIN ALMACÉN"

    if obra_nombre:
        label = f"{obra_nombre} · {almacen_nombre}"
    else:
        label = almacen_nombre

    return {
        "obra": obra_nombre,
        "almacen": almacen_nombre,
        "label": label,
    }

def _alm_ux1d_lookup_stocks(recurso_id):
    # OBRA_MOVIL_ALM_UX2B4_AGRUPAR_STOCK_OK
    from django.apps import apps
    from django.db import models

    try:
        rid = int(recurso_id)
    except Exception:
        return []

    grouped = {}

    qty_priority = [
        "stock_actual", "stock", "existencias", "existencia",
        "saldo", "cantidad_actual", "cantidad", "unidades"
    ]

    for model in apps.get_models():
        model_name = model.__name__.lower()

        fields = list(model._meta.fields)

        recurso_fks = [
            f for f in fields
            if getattr(f, "remote_field", None)
            and f.remote_field
            and "recurso" in f.name.lower()
        ]

        almacen_fks = [
            f for f in fields
            if getattr(f, "remote_field", None)
            and f.remote_field
            and "almacen" in f.name.lower()
        ]

        if not recurso_fks or not almacen_fks:
            continue

        numeric_fields = [
            f for f in fields
            if isinstance(f, (
                models.IntegerField,
                models.PositiveIntegerField,
                models.DecimalField,
                models.FloatField,
            ))
        ]

        if not numeric_fields:
            continue

        has_stock_semantics = (
            "stock" in model_name
            or "recursoalmacen" in model_name
            or any(("stock" in f.name.lower() or "exist" in f.name.lower() or "saldo" in f.name.lower()) for f in numeric_fields)
        )

        if not has_stock_semantics:
            continue

        qty_field = None

        for wanted in qty_priority:
            for f in numeric_fields:
                if f.name.lower() == wanted:
                    qty_field = f
                    break
            if qty_field:
                break

        if not qty_field:
            qty_field = numeric_fields[0]

        recurso_fk = recurso_fks[0]
        almacen_fk = almacen_fks[0]

        try:
            qs = model.objects.filter(**{recurso_fk.attname: rid})[:200]
        except Exception:
            continue

        for row in qs:
            try:
                almacen_obj = getattr(row, almacen_fk.name)
                almacen_id = getattr(almacen_obj, "pk", None)
                display = _alm_ux2b2_almacen_display(almacen_obj)
                qty = getattr(row, qty_field.name, None)
            except Exception:
                continue

            try:
                qty_float = float(qty or 0)
            except Exception:
                qty_float = 0

            if abs(qty_float) < 0.000001:
                continue

            # Agrupar por almacén real, no por cantidad.
            # Antes se usaba (almacen_id, qty), lo que duplicaba el mismo almacén si había varias filas.
            key = str(almacen_id or display.get("label") or display.get("almacen") or "")

            if not key:
                continue

            if key not in grouped:
                grouped[key] = {
                    "id": str(almacen_id or ""),
                    "nombre": display.get("almacen") or "Almacén",
                    "obra": display.get("obra") or "",
                    "label": display.get("label") or display.get("almacen") or "Almacén",
                    "stock_numeric": 0.0,
                    "sources_count": 0,
                }

            grouped[key]["stock_numeric"] += qty_float
            grouped[key]["sources_count"] += 1

    results = []

    for item in grouped.values():
        stock_numeric = item.get("stock_numeric") or 0

        if abs(stock_numeric) < 0.000001:
            continue

        item["stock"] = _alm_ux1d_format_number(stock_numeric)

        label_norm = str(item.get("label") or "").strip().upper()
        item["is_sin_almacen"] = label_norm in {"SIN ALMACÉN", "SIN ALMACEN"}
        item["selectable"] = bool(str(item.get("id") or "").strip())

        results.append(item)

    results.sort(
        key=lambda x: (
            -float(x.get("stock_numeric") or 0),
            str(x.get("label") or ""),
        )
    )

    return results[:12]

def _alm_ux1d_enrich_option(option):
    parsed = _alm_ux1d_parse_article_text(option.get("text", ""))
    almacenes = _alm_ux1d_lookup_stocks(option.get("id"))

    total = None
    try:
        total = sum(float(str(a.get("stock", "0")).replace(",", ".")) for a in almacenes)
    except Exception:
        total = None

    return {
        "id": str(option.get("id") or ""),
        "text": option.get("text") or "",
        "codigo": parsed.get("codigo") or "",
        "nombre": parsed.get("nombre") or option.get("text") or "",
        "tipo": parsed.get("tipo") or "",
        "unidad": parsed.get("unidad") or "",
        "almacenes": almacenes,
        "almacenes_count": len(almacenes),
        "stock_total": _alm_ux1d_format_number(total) if total is not None else "",
    }


# OBRA_MOVIL_ALM_UX1G_RELEVANCE_OK
def _alm_ux1g_normalize(value):
    import unicodedata
    import re

    text = str(value or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def _alm_ux1g_words(value):
    return [w for w in _alm_ux1g_normalize(value).split(" ") if w]

def _alm_ux1g_numeric(value):
    try:
        return float(str(value or "0").replace(",", "."))
    except Exception:
        return 0.0

def _alm_ux1g_relevance_score(item, query):
    """
    Ordena resultados para uso real en tablet:
    - código exacto / código empieza
    - nombre exacto / nombre empieza
    - palabra empieza por búsqueda
    - contiene búsqueda
    - stock y almacenes con stock como desempate
    Penaliza coincidencias internas tipo ATORNILLADO cuando se busca TORNI,
    porque no empieza por TORNI aunque lo contenga.
    """
    q = _alm_ux1g_normalize(query)

    if not q:
        return 0

    codigo = _alm_ux1g_normalize(item.get("codigo") or "")
    nombre = _alm_ux1g_normalize(item.get("nombre") or "")
    text = _alm_ux1g_normalize(item.get("text") or "")
    full = " ".join([codigo, nombre, text]).strip()
    words = _alm_ux1g_words(full)

    score = 0

    if codigo == q:
        score += 2000
    elif codigo.startswith(q):
        score += 1600
    elif q in codigo:
        score += 700

    if nombre == q:
        score += 1800
    elif nombre.startswith(q):
        score += 1500
    elif any(w == q for w in words):
        score += 1400
    elif any(w.startswith(q) for w in words):
        score += 1200
    elif q in nombre:
        score += 500
    elif q in full:
        score += 250

    # Extra para búsquedas parciales donde el usuario escribe raíz: torni, tubo, cable...
    # Si una palabra empieza por la búsqueda, debe ganar a una coincidencia interna.
    if any(w.startswith(q) for w in words):
        score += 450

    # Desempate por stock real.
    almacenes_count = int(item.get("almacenes_count") or 0)
    stock_total = _alm_ux1g_numeric(item.get("stock_total"))

    if almacenes_count > 0:
        score += 80 + min(almacenes_count, 5) * 10

    if stock_total > 0:
        score += 60 + min(stock_total, 1000) / 100

    # Pequeña penalización si la coincidencia solo aparece dentro de una palabra larga.
    # Ejemplo: TORNI dentro de ATORNILLADO.
    if q in full and not any(w.startswith(q) for w in words):
        score -= 180

    return score

@login_required
@require_GET
def almacen_rapido_articulos_api(request):
    q = (request.GET.get("q") or request.GET.get("q_recurso") or "").strip()
    tipo = (request.GET.get("tipo_recurso") or request.GET.get("tipo") or "").strip()
    # BUSQUEDAS_ARTICULOS_SIN_LIMITE_V1
    # Devolver todas las coincidencias válidas.

    if len(q) < 1:
        return JsonResponse({
            "ok": True,
            "q": q,
            "results": [],
            "message": "Escribe al menos 1 carácter.",
        })

    old_get = request.GET
    query = old_get.copy()
    query["q_recurso"] = q

    if tipo:
        query["tipo_recurso"] = tipo

    try:
        request.GET = query
        response = almacen_rapido(request)

        if hasattr(response, "render"):
            response = response.render()

        html = response.content.decode("utf-8", errors="replace")
    finally:
        request.GET = old_get

    options = _alm_ux1d_parse_recurso_options(html)
    enriched = [_alm_ux1d_enrich_option(opt) for opt in options]
    results = sorted(
        enriched,
        key=lambda item: _alm_ux1g_relevance_score(item, q),
        reverse=True,
    )

    return JsonResponse({
        "ok": True,
        "q": q,
        "tipo_recurso": tipo,
        "count": len(results),
        "ordering": "OBRA_MOVIL_ALM_UX1G_RELEVANCE_OK",
        "results": results,
    })



# OBRA_MOVIL_DIRECT_FLOW_OK
def obra_movil_almacen_direct_redirect(request):
    from django.shortcuts import redirect
    return redirect("/app/obra-movil/almacen/rapido/")

def obra_movil_produccion_direct_redirect(request):
    from django.shortcuts import redirect
    return redirect("/app/obra-movil/produccion/nueva/")

# OBRA_MOVIL_ALM_UX2B5_SIN_ALMACEN_OK


# OBRA_MOVIL_ALM_UX2B7_DESTINO_PLANIFICACION_OK
def almacen_rapido_destino_planificacion_api(request):
    from django.apps import apps
    from django.db.models import Exists, OuterRef, Q
    from django.http import JsonResponse

    def s(value):
        return str(value or "").strip()

    def item(pk, text):
        return {"id": str(pk), "text": s(text)}

    def scoped(qs):
        try:
            return _scoped(qs, request)
        except Exception:
            try:
                return _apply_mobile_team_scope(qs, request)
            except Exception:
                return qs

    def obra_label(o):
        codigo = s(getattr(o, "codigo", "")) or s(getattr(o, "legacy_cod_obra", ""))
        nombre = s(getattr(o, "nombre", "")) or s(o)
        return f"{codigo} · {nombre}" if codigo and codigo not in nombre else nombre

    def fase_label(f):
        codigo = s(getattr(f, "legacy_cod_fase", ""))
        nombre = s(getattr(f, "nombre", "")) or s(f)
        return f"{codigo} · {nombre}" if codigo and codigo not in nombre else nombre

    def unidad_label(u):
        edificio = s(getattr(u, "edificio", ""))
        vivienda = s(getattr(u, "vivienda", ""))
        nivel = s(getattr(u, "nivel", "")) or s(getattr(u, "planta", ""))

        parts = []
        if edificio:
            parts.append(edificio)
        if vivienda:
            parts.append(f"Viv. {vivienda}")
        if nivel:
            parts.append(nivel)

        return " · ".join(parts) or s(u)

    def capitulo_label(c):
        codigo = s(getattr(c, "codigo", ""))
        nombre = s(getattr(c, "nombre", "")) or s(c)
        return f"{codigo} · {nombre}" if codigo and codigo not in nombre else nombre

    def partida_label(p):
        codigo = s(getattr(p, "codigo", ""))
        nombre = s(getattr(p, "nombre", "")) or s(p)

        cap = getattr(p, "capitulo", None)
        cap_codigo = s(getattr(cap, "codigo", "")) if cap else ""

        prefix = " · ".join([x for x in [cap_codigo, codigo] if x])
        return f"{prefix} · {nombre}" if prefix and prefix not in nombre else nombre

    ObraPlanificacion = apps.get_model("planificacion_obra", "ObraPlanificacion")
    FaseObra = apps.get_model("planificacion_obra", "FaseObra")
    UnidadObra = apps.get_model("planificacion_obra", "UnidadObra")
    TareaObra = apps.get_model("planificacion_obra", "TareaObra")
    CapituloCatalogo = apps.get_model("planificacion_obra", "CapituloCatalogo")
    PartidaCatalogo = apps.get_model("planificacion_obra", "PartidaCatalogo")
    AlmacenObra = apps.get_model("planificacion_obra", "AlmacenObra")

    almacen_id = s(request.GET.get("almacen"))
    obra_id = s(request.GET.get("obra"))
    fase_id = s(request.GET.get("edificio") or request.GET.get("fase"))
    unidad_id = s(request.GET.get("vivienda") or request.GET.get("unidad_obra"))
    planta = s(request.GET.get("planta") or request.GET.get("planta_trabajo"))
    capitulo_id = s(request.GET.get("capitulo"))
    partida_id = s(request.GET.get("partida"))

    obras_qs = scoped(ObraPlanificacion.objects.all()).order_by("legacy_cod_obra", "codigo", "nombre", "id")

    almacen = None
    if almacen_id:
        try:
            almacen = scoped(AlmacenObra.objects.select_related("obra").all()).filter(pk=almacen_id).first()
        except Exception:
            almacen = None

    if almacen and getattr(almacen, "obra_id", None):
        obras_qs = obras_qs.filter(pk=almacen.obra_id)
        if not obra_id:
            obra_id = str(almacen.obra_id)

    obras = [item(o.pk, obra_label(o)) for o in obras_qs[:200]]

    fases = []
    viviendas = []
    plantas = []
    capitulos = []
    partidas = []

    if obra_id:
        fases_qs = scoped(
            FaseObra.objects.filter(obra_id=obra_id)
        ).order_by("legacy_cod_fase", "nombre", "id")

        fases = [item(f.pk, fase_label(f)) for f in fases_qs[:300]]

        unidades_qs = scoped(
            UnidadObra.objects.select_related("obra", "fase").filter(obra_id=obra_id)
        ).order_by("edificio", "vivienda", "nivel", "id")

        tareas_qs = scoped(
            TareaObra.objects.select_related("unidad_obra", "capitulo", "partida").filter(obra_id=obra_id)
        ).order_by("legacy_cod_fase", "legacy_cod_vivienda", "legacy_planta", "legacy_capitulo", "legacy_partida", "id")

        fase_obj = None
        if fase_id:
            fase_obj = fases_qs.filter(pk=fase_id).first()
            unidades_qs = unidades_qs.filter(fase_id=fase_id)

            if fase_obj and getattr(fase_obj, "legacy_cod_fase", None) is not None:
                tareas_qs = tareas_qs.filter(legacy_cod_fase=fase_obj.legacy_cod_fase)

        viviendas = [item(u.pk, unidad_label(u)) for u in unidades_qs[:500]]

        if unidad_id:
            unidades_qs = unidades_qs.filter(pk=unidad_id)
            tareas_qs = tareas_qs.filter(unidad_obra_id=unidad_id)

        plantas_raw = (
            tareas_qs.exclude(legacy_planta__isnull=True)
            .exclude(legacy_planta="")
            .values_list("legacy_planta", flat=True)
            .distinct()
            .order_by("legacy_planta")
        )

        plantas = [{"id": s(p), "text": s(p)} for p in plantas_raw[:300]]

        if planta:
            tareas_qs = tareas_qs.filter(legacy_planta=planta)

        capitulo_ids = (
            tareas_qs.exclude(capitulo_id__isnull=True)
            .values_list("capitulo_id", flat=True)
            .distinct()
        )

        capitulos_qs = scoped(
            CapituloCatalogo.objects.filter(pk__in=capitulo_ids)
        ).order_by("codigo", "orden", "nombre", "id")

        capitulos = [item(c.pk, capitulo_label(c)) for c in capitulos_qs[:300]]

        if capitulo_id:
            tareas_qs = tareas_qs.filter(capitulo_id=capitulo_id)

        partida_ids = (
            tareas_qs.exclude(partida_id__isnull=True)
            .values_list("partida_id", flat=True)
            .distinct()
        )

        partidas_qs = scoped(
            PartidaCatalogo.objects.select_related("capitulo").filter(pk__in=partida_ids)
        ).order_by("capitulo__codigo", "codigo", "nombre", "id")

        partidas = [item(p.pk, partida_label(p)) for p in partidas_qs[:500]]

        if partida_id:
            tareas_qs = tareas_qs.filter(partida_id=partida_id)

    return JsonResponse({
        "ok": True,
        "marker": "OBRA_MOVIL_ALM_UX2B7_DESTINO_PLANIFICACION_OK",
        "selected": {
            "obra": obra_id,
            "edificio": fase_id,
            "vivienda": unidad_id,
            "planta": planta,
            "capitulo": capitulo_id,
            "partida": partida_id,
        },
        "obras": obras,
        "edificios": fases,
        "viviendas": viviendas,
        "plantas": plantas,
        "capitulos": capitulos,
        "partidas": partidas,
    })

# OBRA_MOVIL_ALM_UX2B8_RESET_SIN_ALMACEN_OK

# OBRA_MOVIL_ALM_UX2B8B_RESET_SIN_ALMACEN_FIX_OK

# OBRA_MOVIL_ALM_UX2B8B_ROBUSTO_OK


# OBRA_MOVIL_ALM_UX2E1_V2_PLANIFICACION_PARTIDA_OK
def _alm_ux2e1_decimal(value):
    from decimal import Decimal

    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "."))
    except Exception:
        return Decimal("0")


# OBRA_MOVIL_ALM_UX2E1_V2_PLANIFICACION_PARTIDA_OK
def _alm_ux2e1_recurso_precio(recurso):
    from decimal import Decimal

    if recurso is None:
        return Decimal("0")

    for name in ("precio_unidad_uso", "ultimo_precio_unidad", "precio_unidad", "precio"):
        if hasattr(recurso, name):
            value = getattr(recurso, name)
            if value not in (None, ""):
                try:
                    return Decimal(str(value))
                except Exception:
                    pass

    return Decimal("0")


# OBRA_MOVIL_ALM_UX2E1_V2_PLANIFICACION_PARTIDA_OK
def _alm_ux2e1_sync_movimiento_a_planificacion(movimiento, request=None):
    """
    Proyecta SALIDA/ROTURA con destino PARTIDA a TareaRecursoReal.
    Idempotente por movimiento_almacen.
    """
    if not movimiento:
        return None

    tipo_mov = str(getattr(movimiento, "tipo_movimiento", "") or "").upper()
    if tipo_mov not in {"SALIDA", "ROTURA"}:
        return None

    raw = getattr(movimiento, "raw_data", None)
    raw = raw if isinstance(raw, dict) else {}

    destino_operativo = raw.get("destino_operativo") if isinstance(raw.get("destino_operativo"), dict) else {}
    destino_tipo = str(destino_operativo.get("tipo") or raw.get("destino") or "").upper()

    if destino_tipo != "PARTIDA" and not getattr(movimiento, "en_partida", False):
        return None

    if not getattr(movimiento, "unidad_obra_id", None) or not getattr(movimiento, "partida_id", None):
        raise ValueError("SALIDA/ROTURA a vivienda-partida requiere unidad_obra y partida completas.")

    from django.utils import timezone
    from planificacion_obra.models import TareaObra, TareaRecursoReal

    existente = TareaRecursoReal.objects.filter(movimiento_almacen=movimiento).first()
    if existente:
        return existente

    tarea = (
        TareaObra.objects
        .filter(
            team_id=movimiento.team_id,
            obra_id=movimiento.obra_id,
            unidad_obra_id=movimiento.unidad_obra_id,
            partida_id=movimiento.partida_id,
        )
        .order_by("-id")
        .first()
    )

    if not tarea:
        raise ValueError("No existe tarea de planificación para la vivienda/partida seleccionada.")

    recurso = movimiento.recurso
    cantidad = abs(_alm_ux2e1_decimal(movimiento.cantidad))
    precio = _alm_ux2e1_recurso_precio(recurso)
    coste = cantidad * precio
    fecha = getattr(movimiento, "fecha_movimiento", None) or timezone.localdate()

    legacy_tipo = getattr(recurso, "tipo", None) or "MATERIAL"

    raw_real = {
        "origen": "almacen_rapido",
        "created_at": timezone.now().isoformat(),
        "creado_desde": "almacen_rapido_salida_partida",
        "movimiento_almacen_id": movimiento.pk,
        "tipo_movimiento": tipo_mov,
        "destino_operativo": destino_operativo or {"tipo": "PARTIDA"},
        "marker": "OBRA_MOVIL_ALM_UX2E1_V2_PLANIFICACION_PARTIDA_OK",
    }

    if request is not None and getattr(request, "user", None) and request.user.is_authenticated:
        raw_real["created_by_user_id"] = request.user.pk

    real = TareaRecursoReal.objects.create(
        team=movimiento.team,
        tarea_obra=tarea,
        unidad_obra=movimiento.unidad_obra,
        partida=movimiento.partida,
        recurso=recurso,
        movimiento_almacen=movimiento,
        legacy_id_movimiento_almacen=movimiento.legacy_id_movimiento,
        legacy_id_recurso_tarea=_alm_ux2e1_v8_next_legacy_id_recurso_tarea(),
        legacy_id_recurso=getattr(recurso, "legacy_id", None),
        legacy_tipo_recurso=legacy_tipo,
        legacy_cod_obra=movimiento.legacy_cod_obra,
        legacy_cod_fase=movimiento.legacy_cod_fase,
        legacy_cod_vivienda=movimiento.legacy_cod_vivienda,
        legacy_planta=movimiento.legacy_planta,
        legacy_capitulo=movimiento.legacy_capitulo,
        legacy_partida=movimiento.legacy_partida,
        unidad=movimiento.unidad or getattr(recurso, "unidad", "") or "",
        cantidad=cantidad,
        precio_unidad=precio,
        costo_recurso=coste,
        costo_recurso_real=coste,
        inicio_recurso_real=fecha,
        fin_recurso_real=fecha,
        control_suministros=True,
        raw_data=raw_real,
    )

    raw_mov = dict(raw)
    raw_mov["_planificacion_recurso_real"] = {
        "marker": "OBRA_MOVIL_ALM_UX2E1_V2_PLANIFICACION_PARTIDA_OK",
        "tarea_obra_id": tarea.pk,
        "tarea_recurso_real_id": real.pk,
        "created_at": timezone.now().isoformat(),
    }
    movimiento.raw_data = raw_mov
    movimiento.save(update_fields=["raw_data"])

    return real



# OBRA_MOVIL_ALM_UX2E1_V6_STOCK_OPERATIVO_OK
def _alm_ux2e1_v6_decimal(value):
    from decimal import Decimal

    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "."))
    except Exception:
        return Decimal("0")


# OBRA_MOVIL_ALM_UX2E1_V6_STOCK_OPERATIVO_OK
def _alm_ux2e1_v6_stock_operativo_movimiento(recurso, almacen):
    """
    Stock operativo en el almacén seleccionado. Prioriza el mismo helper que alimenta
    las tarjetas visuales del almacén rápido.
    """
    if not recurso or not almacen:
        return _q_stock(getattr(recurso, "stock", 0))

    try:
        fn = globals().get("_alm_ux1d_lookup_stocks")
        if callable(fn):
            rows = fn(recurso.pk)

            if isinstance(rows, dict):
                rows = rows.get("almacenes") or rows.get("results") or []

            for row in rows or []:
                if not isinstance(row, dict):
                    continue

                row_id = str(row.get("id") or row.get("almacen_id") or "")
                if row_id == str(almacen.pk):
                    if row.get("stock_numeric") is not None:
                        return _q_stock(row.get("stock_numeric"))
                    return _q_stock(row.get("stock"))
    except Exception:
        pass

    try:
        from planificacion_obra.models import RecursoAlmacenMovimiento

        ultimo = (
            RecursoAlmacenMovimiento.objects
            .filter(recurso=recurso, almacen=almacen)
            .exclude(quedan__isnull=True)
            .order_by("-fecha_movimiento", "-hora_movimiento", "-created_at", "-pk")
            .first()
        )

        if ultimo is not None:
            return _q_stock(ultimo.quedan)
    except Exception:
        pass

    return _q_stock(getattr(recurso, "stock", 0))



# OBRA_MOVIL_ALM_UX2E1_V7_STOCK_ALMACEN_REAL_OK
def _alm_ux2e1_v7_decimal(value):
    from decimal import Decimal

    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "."))
    except Exception:
        return Decimal("0")


# OBRA_MOVIL_ALM_UX2E1_V7_STOCK_ALMACEN_REAL_OK
def _alm_ux2e1_v7_stock_almacen_real(recurso, almacen):
    """
    Stock operativo real del recurso en el almacén seleccionado.
    Debe coincidir con el stock visual agrupado por almacén.
    """
    if not recurso or not almacen:
        return _q_stock(getattr(recurso, "stock", 0))

    try:
        from django.db.models import Sum
        from planificacion_obra.models import RecursoAlmacenMovimiento

        agg = (
            RecursoAlmacenMovimiento.objects
            .filter(recurso=recurso, almacen=almacen)
            .exclude(quedan__isnull=True)
            .aggregate(total=Sum("quedan"))
        )

        total = _q_stock(agg.get("total"))

        if total != 0:
            return total
    except Exception:
        pass

    return _q_stock(getattr(recurso, "stock", 0))



# OBRA_MOVIL_ALM_UX2E1_V8_LEGACY_RECURSO_TAREA_OK
def _alm_ux2e1_v8_next_legacy_id_recurso_tarea():
    """
    TareaRecursoReal.legacy_id_recurso_tarea es NOT NULL.
    Para altas creadas desde Obra móvil usamos una secuencia funcional MAX + 1,
    equivalente al criterio legacy usado en sincronizaciones/importaciones.
    """
    try:
        from django.db.models import Max
        from planificacion_obra.models import TareaRecursoReal

        value = (
            TareaRecursoReal.objects
            .exclude(legacy_id_recurso_tarea__isnull=True)
            .aggregate(max_value=Max("legacy_id_recurso_tarea"))
            .get("max_value")
        )

        if value is None:
            return 1

        return int(value) + 1

    except Exception:
        try:
            from planificacion_obra.models import TareaRecursoReal
            return int(TareaRecursoReal.objects.count()) + 1
        except Exception:
            return 1



# OBRA_MOVIL_ALM_UX3_MOVIMIENTOS_IMPUTAR_OK
from django.contrib.auth.decorators import login_required as _alm_ux3_login_required


# OBRA_MOVIL_ALM_UX3_MOVIMIENTOS_IMPUTAR_OK
def _alm_ux3_apply_team_scope(qs, request):
    user = getattr(request, "user", None)

    try:
        active_team_id = request.session.get("active_team_id")
    except Exception:
        active_team_id = None

    if active_team_id not in (None, "", "all"):
        try:
            from planificacion_obra.utils import get_active_team
            active_team = get_active_team(request)
        except Exception:
            active_team = None

        if active_team is not None:
            return qs.filter(team=active_team)

    if user is not None and not getattr(user, "is_superuser", False) and hasattr(user, "teams"):
        return qs.filter(team__in=user.teams.all())

    return qs


# OBRA_MOVIL_ALM_UX3_MOVIMIENTOS_IMPUTAR_OK
def _alm_ux3_is_pendiente_persona(mov):
    return (
        getattr(mov, "empleado_id", None) is not None
        and getattr(mov, "unidad_obra_id", None) is None
        and getattr(mov, "partida_id", None) is None
        and not bool(getattr(mov, "en_partida", False))
        and str(getattr(mov, "tipo_movimiento", "") or "").upper() in {"SALIDA", "ROTURA"}
    )


# OBRA_MOVIL_ALM_UX3_MOVIMIENTOS_IMPUTAR_OK
def _alm_ux3_destino_label(mov):
    if _alm_ux3_is_pendiente_persona(mov):
        return "Persona · pendiente de imputar"

    if getattr(mov, "partida_id", None) or bool(getattr(mov, "en_partida", False)):
        return "Partida"

    if getattr(mov, "empleado_id", None):
        return "Persona"

    return "Almacén"


# OBRA_MOVIL_ALM_UX3_MOVIMIENTOS_IMPUTAR_OK
def _alm_ux3_label_unidad(unidad):
    if unidad is None:
        return ""

    obra = getattr(unidad, "obra", None)
    obra_txt = str(obra) if obra else ""

    parts = []
    if obra_txt:
        parts.append(obra_txt)

    for name in ("edificio", "fase", "bloque"):
        value = getattr(unidad, name, None)
        if value not in (None, ""):
            parts.append(str(value))
            break

    vivienda = (
        getattr(unidad, "vivienda", None)
        or getattr(unidad, "legacy_cod_vivienda", None)
        or getattr(unidad, "cod_vivienda", None)
    )
    if vivienda not in (None, ""):
        vivienda = str(vivienda)
        parts.append(vivienda if vivienda.lower().startswith("viv") else f"Viv. {vivienda}")

    planta = (
        getattr(unidad, "nivel", None)
        or getattr(unidad, "planta", None)
        or getattr(unidad, "legacy_planta", None)
    )
    if planta not in (None, ""):
        parts.append(str(planta))

    return " · ".join(parts) or str(unidad)


# OBRA_MOVIL_ALM_UX3_MOVIMIENTOS_IMPUTAR_OK
def _alm_ux3_label_partida(partida):
    if partida is None:
        return ""

    cap = getattr(partida, "capitulo", None)
    cap_code = getattr(cap, "codigo", "") if cap else ""
    codigo = getattr(partida, "codigo", "") or ""
    nombre = getattr(partida, "nombre", "") or ""

    head = " · ".join([x for x in [cap_code, codigo] if x])
    if head and nombre:
        return f"{head} · {nombre}"
    return head or nombre or str(partida)


# OBRA_MOVIL_ALM_UX3_MOVIMIENTOS_IMPUTAR_OK
@_alm_ux3_login_required
def almacen_movimientos_desktop_redirect(request):
    """Compatibility entry point: keep old bookmarks, render desktop history."""
    from django.shortcuts import redirect
    from django.urls import reverse

    target = reverse("planificacion_obra:almacen_movimientos_general")
    if request.GET:
        target = f"{target}?{request.GET.urlencode()}"
    return redirect(target)


@_alm_ux3_login_required
def almacen_movimientos(request):
    from django.core.paginator import Paginator
    from django.db.models import Exists, OuterRef, Q
    from django.shortcuts import render

    from planificacion_obra.models import (
        AlmacenObra,
        EmpleadoObra,
        ObraPlanificacion,
        RecursoAlmacenMovimiento,
        TareaRecursoReal,
    )
    from .movimientos_almacen import classify_movement, origin_label, permission_allowed

    qs = (
        RecursoAlmacenMovimiento.objects
        .select_related(
            "team",
            "almacen",
            "almacen__obra",
            "obra",
            "unidad_obra",
            "unidad_obra__obra",
            "partida",
            "partida__capitulo",
            "empleado",
            "recurso",
        )
        .annotate(tiene_real=Exists(TareaRecursoReal.objects.filter(movimiento_almacen_id=OuterRef("pk"))))
    )

    qs = _alm_ux3_apply_team_scope(qs, request)

    q = (request.GET.get("q") or "").strip()
    tipo = (request.GET.get("tipo") or "").strip()
    destino = (request.GET.get("destino") or "").strip().upper()
    estado = (request.GET.get("estado") or "").strip().upper()
    empleado_id = (request.GET.get("empleado") or "").strip()
    almacen_id = (request.GET.get("almacen") or "").strip()
    obra_id = (request.GET.get("obra") or "").strip()
    fecha_desde = (request.GET.get("fecha_desde") or "").strip()
    fecha_hasta = (request.GET.get("fecha_hasta") or "").strip()

    if q:
        q_filter = (
            Q(recurso__nombre__icontains=q)
            | Q(legacy_cod_recurso__icontains=q)
            | Q(cod_albaran__icontains=q)
            | Q(cod_proveedor__icontains=q)
            | Q(empleado__nombre__icontains=q)
            | Q(almacen__nombre__icontains=q)
            | Q(observaciones__icontains=q)
        )

        if q.isdigit():
            q_int = int(q)
            q_filter = q_filter | Q(pk=q_int) | Q(legacy_id_movimiento=q_int)

        qs = qs.filter(q_filter)

    if tipo:
        qs = qs.filter(tipo_movimiento=tipo)

    if empleado_id:
        qs = qs.filter(empleado_id=empleado_id)

    if almacen_id:
        qs = qs.filter(almacen_id=almacen_id)

    if obra_id:
        qs = qs.filter(Q(obra_id=obra_id) | Q(almacen__obra_id=obra_id) | Q(unidad_obra__obra_id=obra_id))

    if fecha_desde:
        qs = qs.filter(fecha_movimiento__gte=fecha_desde)

    if fecha_hasta:
        qs = qs.filter(fecha_movimiento__lte=fecha_hasta)

    if destino == "PERSONA":
        qs = qs.filter(empleado__isnull=False, en_partida=False)
    elif destino == "PARTIDA":
        qs = qs.filter(Q(en_partida=True) | Q(partida__isnull=False))
    elif destino == "ALMACEN":
        qs = qs.filter(empleado__isnull=True, unidad_obra__isnull=True, partida__isnull=True, en_partida=False)

    if estado in {"PENDIENTE", "PENDIENTE_PERSONA"}:
        qs = qs.filter(
            empleado__isnull=False,
            unidad_obra__isnull=True,
            partida__isnull=True,
            en_partida=False,
            tipo_movimiento__in=["SALIDA", "ROTURA"],
        )
    elif estado == "IMPUTADO":
        qs = qs.filter(Q(en_partida=True) | Q(partida__isnull=False))

    qs = qs.order_by("-fecha_movimiento", "-hora_movimiento", "-created_at", "-pk")

    total = qs.count()

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    for mov in page_obj.object_list:
        mov.ux3_pendiente_persona = _alm_ux3_is_pendiente_persona(mov)
        mov.ux3_destino_label = _alm_ux3_destino_label(mov)
        mov.ux3_unidad_label = _alm_ux3_label_unidad(getattr(mov, "unidad_obra", None))
        mov.ux3_partida_label = _alm_ux3_label_partida(getattr(mov, "partida", None))
        mov.origin_code = classify_movement(mov)
        mov.origin_label = origin_label(mov.origin_code)
        mov.can_edit = mov.origin_code == "MANUAL" and permission_allowed(request.user, "planificacion_obra.change_recursoalmacenmovimiento")
        mov.can_delete = mov.origin_code == "MANUAL" and permission_allowed(request.user, "planificacion_obra.delete_recursoalmacenmovimiento")
        if mov.origin_code == "MANUAL":
            mov.blocked_reason = "" if (mov.can_edit or mov.can_delete) else "Bloqueado: faltan permisos funcionales."
        else:
            mov.blocked_reason = f"Bloqueado: {mov.origin_label}."

    scope_movs = _alm_ux3_apply_team_scope(RecursoAlmacenMovimiento.objects.all(), request)
    scope_team_ids = scope_movs.values_list("team_id", flat=True).distinct()

    empleados = EmpleadoObra.objects.filter(
        team_id__in=scope_team_ids,
        tipo=EmpleadoObra.Tipo.ADMINISTRADA,
        situacion=EmpleadoObra.Situacion.ACTIVO,
        fecha_baja__isnull=True,
    ).exclude(
        rrhh_empleado_id__isnull=True,
    ).exclude(
        legacy_id=0,
    ).order_by("nombre", "id")

    almacenes = AlmacenObra.objects.filter(team_id__in=scope_team_ids).select_related("obra").order_by("obra__legacy_cod_obra", "nombre", "id")
    obras = ObraPlanificacion.objects.filter(team_id__in=scope_team_ids).order_by("legacy_cod_obra", "nombre", "id")

    pendientes_count = scope_movs.filter(
        empleado__isnull=False,
        unidad_obra__isnull=True,
        partida__isnull=True,
        en_partida=False,
        tipo_movimiento__in=["SALIDA", "ROTURA"],
    ).count()

    context = {}
    try:
        context.update(_dashboard_context(request))
    except Exception:
        pass

    context.update({
        "alm_ux3_marker": "OBRA_MOVIL_ALM_UX3_MOVIMIENTOS_IMPUTAR_OK",
        "page_obj": page_obj,
        "movimientos": page_obj.object_list,
        "total": total,
        "pendientes_count": pendientes_count,
        "filtros": {
            "q": q,
            "tipo": tipo,
            "destino": destino,
            "estado": estado,
            "empleado": empleado_id,
            "almacen": almacen_id,
            "obra": obra_id,
            "fecha_desde": fecha_desde,
            "fecha_hasta": fecha_hasta,
        },
        "empleados": empleados,
        "almacenes": almacenes,
        "obras": obras,
        "tipos": ["ENTRADA", "SALIDA", "CONTROL_STOCK", "ROTURA"],
    })

    return render(request, "obra_movil/almacen_movimientos.html", context)


# OBRA_MOVIL_ALM_UX3_MOVIMIENTOS_IMPUTAR_OK
@_alm_ux3_login_required
def almacen_movimiento_imputar(request, pk):
    from django.contrib import messages
    from django.db import transaction
    from django.shortcuts import get_object_or_404, redirect, render
    from django.urls import reverse
    from django.utils import timezone

    from planificacion_obra.models import (
        PartidaCatalogo,
        RecursoAlmacenMovimiento,
        TareaObra,
        TareaRecursoReal,
        UnidadObra,
    )

    base_qs = (
        RecursoAlmacenMovimiento.objects
        .select_related(
            "team",
            "almacen",
            "almacen__obra",
            "obra",
            "unidad_obra",
            "partida",
            "empleado",
            "recurso",
        )
    )
    base_qs = _alm_ux3_apply_team_scope(base_qs, request)

    mov = get_object_or_404(base_qs, pk=pk)

    if not _alm_ux3_is_pendiente_persona(mov):
        messages.warning(request, "Este movimiento no está pendiente de imputar a partida.")
        return redirect("obra_movil:almacen_movimientos")

    tareas_base = TareaObra.objects.filter(team_id=mov.team_id).select_related(
        "obra",
        "unidad_obra",
        "partida",
        "partida__capitulo",
    )

    unidad_ids = tareas_base.exclude(unidad_obra__isnull=True).values_list("unidad_obra_id", flat=True).distinct()
    partida_ids = tareas_base.exclude(partida__isnull=True).values_list("partida_id", flat=True).distinct()

    unidades = list(
        UnidadObra.objects
        .filter(pk__in=unidad_ids)
        .select_related("obra")
        .order_by("obra__legacy_cod_obra", "edificio", "vivienda", "nivel", "id")[:1000]
    )

    partidas = list(
        PartidaCatalogo.objects
        .filter(pk__in=partida_ids)
        .select_related("capitulo")
        .order_by("capitulo__codigo", "codigo", "nombre", "id")[:1000]
    )

    for unidad in unidades:
        unidad.ux3_label = _alm_ux3_label_unidad(unidad)

    for partida in partidas:
        partida.ux3_label = _alm_ux3_label_partida(partida)

    selected_unidad = ""
    selected_partida = ""

    if request.method == "POST":
        selected_unidad = (request.POST.get("unidad_obra") or "").strip()
        selected_partida = (request.POST.get("partida") or "").strip()

        unidad = UnidadObra.objects.filter(pk=selected_unidad).select_related("obra").first() if selected_unidad else None
        partida = PartidaCatalogo.objects.filter(pk=selected_partida).select_related("capitulo").first() if selected_partida else None

        if not unidad or not partida:
            messages.error(request, "Para imputar debes seleccionar vivienda/unidad y partida.")
        else:
            tarea = (
                tareas_base
                .filter(unidad_obra=unidad, partida=partida)
                .order_by("-id")
                .first()
            )

            if not tarea:
                messages.error(request, "No existe tarea de planificación para esa vivienda y partida.")
            else:
                with transaction.atomic():
                    # OBRA_MOVIL_ALM_UX3C_SELECT_FOR_UPDATE_OK
                    # Bloquear solo la fila del movimiento. No usar select_related aquí:
                    # PostgreSQL no permite FOR UPDATE sobre el lado nullable de outer joins.
                    mov_locked = (
                        RecursoAlmacenMovimiento.objects
                        .select_for_update()
                        .get(pk=mov.pk)
                    )

                    if TareaRecursoReal.objects.filter(movimiento_almacen=mov_locked).exists():
                        messages.warning(request, "Este movimiento ya tenía recurso real vinculado.")
                        return redirect("obra_movil:almacen_movimientos")

                    raw = mov_locked.raw_data if isinstance(mov_locked.raw_data, dict) else {}
                    raw = dict(raw)
                    raw["destino_operativo_anterior"] = raw.get("destino_operativo")
                    raw["destino_operativo"] = {
                        "tipo": "PARTIDA",
                        "origen": "PERSONA",
                        "empleado_id": mov_locked.empleado_id,
                    }
                    raw["_imputacion_partida"] = {
                        "marker": "OBRA_MOVIL_ALM_UX3_MOVIMIENTOS_IMPUTAR_OK",
                        "tarea_obra_id": tarea.pk,
                        "unidad_obra_id": unidad.pk,
                        "partida_id": partida.pk,
                        "empleado_id": mov_locked.empleado_id,
                        "created_at": timezone.now().isoformat(),
                        "created_by_user_id": getattr(request.user, "pk", None),
                    }

                    mov_locked.unidad_obra = unidad
                    mov_locked.partida = partida
                    mov_locked.obra = tarea.obra or getattr(unidad, "obra", None) or mov_locked.obra
                    mov_locked.en_partida = True
                    mov_locked.legacy_cod_obra = getattr(mov_locked.obra, "legacy_cod_obra", None)
                    mov_locked.legacy_cod_fase = getattr(unidad, "legacy_cod_fase", None)
                    mov_locked.legacy_cod_vivienda = (
                        getattr(unidad, "legacy_cod_vivienda", None)
                        or getattr(unidad, "vivienda", "")
                        or ""
                    )
                    mov_locked.legacy_planta = (
                        getattr(tarea, "legacy_planta", None)
                        or getattr(unidad, "nivel", "")
                        or ""
                    )
                    mov_locked.legacy_capitulo = (
                        getattr(tarea, "legacy_capitulo", None)
                        or getattr(getattr(partida, "capitulo", None), "codigo", "")
                        or ""
                    )
                    mov_locked.legacy_partida = (
                        getattr(tarea, "legacy_partida", None)
                        or getattr(partida, "codigo", "")
                        or ""
                    )
                    mov_locked.raw_data = raw

                    mov_locked.save(update_fields=[
                        "obra",
                        "unidad_obra",
                        "partida",
                        "en_partida",
                        "legacy_cod_obra",
                        "legacy_cod_fase",
                        "legacy_cod_vivienda",
                        "legacy_planta",
                        "legacy_capitulo",
                        "legacy_partida",
                        "raw_data",
                    ])

                    real = _alm_ux2e1_sync_movimiento_a_planificacion(mov_locked, request=request)

                    messages.success(
                        request,
                        f"Movimiento #{mov_locked.legacy_id_movimiento} imputado a partida. Recurso real #{real.pk if real else '—'} creado.",
                    )

                    return redirect(f"{reverse('obra_movil:almacen_movimientos')}?estado=PENDIENTE")

    context = {}
    try:
        context.update(_dashboard_context(request))
    except Exception:
        pass

    mov.ux3_destino_label = _alm_ux3_destino_label(mov)

    context.update({
        "alm_ux3_marker": "OBRA_MOVIL_ALM_UX3_MOVIMIENTOS_IMPUTAR_OK",
        "mov": mov,
        "unidades": unidades,
        "partidas": partidas,
        "selected_unidad": selected_unidad,
        "selected_partida": selected_partida,
    })

    return render(request, "obra_movil/almacen_movimiento_imputar.html", context)


# OBRA_MOVIL_ALM_UX3_FIX_HUMANIZE_Q_MOVIMIENTO_OK

# OBRA_MOVIL_ALM_UX3C_SELECT_FOR_UPDATE_OK


# =============================================================================
# GAS UX 1A · Salida rápida GASOIL a vehículo
# =============================================================================
def _gas_ux1a_decimal(value, field_label="valor"):
    from decimal import Decimal, InvalidOperation

    raw = str(value or "").strip().replace(" ", "")
    if not raw:
        raise ValueError(f"{field_label} es obligatorio.")

    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")

    try:
        val = Decimal(raw)
    except InvalidOperation:
        raise ValueError(f"{field_label} no es válido.")

    if val <= 0:
        raise ValueError(f"{field_label} debe ser mayor que cero.")

    return val


def _gas_ux1a_get_base_objects():
    from django.db.models import Q
    from planificacion_obra.models import AlmacenObra, RecursoCatalogo

    recurso = (
        RecursoCatalogo.objects
        .select_for_update()
        .filter(legacy_id=167, nombre__iexact="GASOIL", tipo="MATERIAL")
        .order_by("id")
        .first()
    )
    if not recurso:
        recurso = (
            RecursoCatalogo.objects
            .select_for_update()
            .filter(legacy_id=167, nombre__icontains="GASOIL")
            .order_by("id")
            .first()
        )

    if not recurso:
        raise ValueError("No se encontró el recurso GASOIL legacy 167.")

    almacen = (
        AlmacenObra.objects
        .select_related("obra", "team")
        .filter(
            Q(legacy_id_almacen__iexact="A10") |
            Q(nombre__icontains="DEPOSITO GASOLEO") |
            Q(nombre__icontains="DEPOSITO GASÓLEO")
        )
        .filter(team_id=recurso.team_id)
        .order_by("id")
        .first()
    )

    if not almacen:
        raise ValueError("No se encontró el almacén A10 · DEPOSITO GASOLEO.")

    return recurso, almacen


@login_required
def gasoil_salida_vehiculo(request):
    """
    GAS_UX1A_SALIDA_VEHICULO_OK

    Pantalla dedicada:
    - Recurso fijo: GASOIL legacy 167
    - Almacén fijo: A10 DEPOSITO GASOLEO
    - Tipo fijo: SALIDA
    - Unidad fija: LTRS
    - Destino operativo: VEHICULO
    """
    from django.contrib import messages
    from django.db import transaction
    from django.db.models import Max
    from django.shortcuts import redirect, render
    from django.utils import timezone
    from datetime import datetime

    from planificacion_obra.models import (
        EmpleadoObra,
        RecursoAlmacenMovimiento,
    )

    error_base = None
    try:
        with transaction.atomic():
            recurso, almacen = _gas_ux1a_get_base_objects()
    except Exception as exc:
        recurso, almacen = None, None
        error_base = str(exc)

    today = timezone.localdate()
    now_hm = timezone.localtime().strftime("%H:%M")

    vehiculos = []
    recargadores = []

    if recurso:
        vehiculos = list(
            RecursoAlmacenMovimiento.objects
            .filter(recurso_id=recurso.id, vehiculo__isnull=False)
            .exclude(vehiculo="")
            .values_list("vehiculo", flat=True)
            .distinct()
            .order_by("vehiculo")[:80]
        )

        recargadores = list(
            RecursoAlmacenMovimiento.objects
            .filter(recurso_id=recurso.id)
            .exclude(observaciones="")
            .values_list("observaciones", flat=True)
            .distinct()
            .order_by("observaciones")[:80]
        )

    empleados = []
    if almacen:
        empleados = list(
            EmpleadoObra.objects
            .filter(team_id=almacen.team_id)
            .exclude(nombre__icontains="GENERICO")
            .exclude(nombre="")
            .order_by("nombre")
            .values_list("nombre", flat=True)[:120]
        )

    recargadores_final = []
    seen = set()
    for item in list(recargadores) + list(empleados):
        val = str(item or "").strip()
        if val and val.upper() not in seen:
            recargadores_final.append(val)
            seen.add(val.upper())

    form_values = {
        "fecha_movimiento": request.POST.get("fecha_movimiento") or str(today),
        "hora_movimiento": request.POST.get("hora_movimiento") or now_hm,
        "cantidad": request.POST.get("cantidad") or "",
        "vehiculo": request.POST.get("vehiculo") or "",
        "kilometraje": request.POST.get("kilometraje") or "",
        "quien_entrega": request.POST.get("quien_entrega") or request.POST.get("quien_recarga") or "",
        "observaciones_extra": request.POST.get("observaciones_extra") or "",
    }

    if request.method == "POST" and not error_base:
        try:
            with transaction.atomic():
                recurso, almacen = _gas_ux1a_get_base_objects()

                cantidad = _gas_ux1a_decimal(form_values["cantidad"], "Cantidad")
                kilometraje = _gas_ux1a_decimal(form_values["kilometraje"], "Kilometraje/KM-HRS")

                vehiculo = str(form_values["vehiculo"] or "").strip().upper()
                quien_entrega = str(form_values["quien_entrega"] or "").strip().upper()
                observaciones_extra = str(form_values["observaciones_extra"] or "").strip()

                if not vehiculo:
                    raise ValueError("Vehículo es obligatorio.")

                if not quien_entrega:
                    raise ValueError("Quién entrega es obligatorio.")

                try:
                    fecha_movimiento = datetime.strptime(form_values["fecha_movimiento"], "%Y-%m-%d").date()
                except Exception:
                    raise ValueError("Fecha no válida.")

                try:
                    hora_movimiento = datetime.strptime(form_values["hora_movimiento"], "%H:%M").time()
                except Exception:
                    raise ValueError("Hora no válida.")

                stock_anterior = recurso.stock or 0
                nuevo_stock = stock_anterior - cantidad

                if nuevo_stock < 0:
                    raise ValueError(f"Stock insuficiente. Stock actual: {stock_anterior} LTRS.")

                empleado = (
                    EmpleadoObra.objects
                    .filter(team_id=almacen.team_id, nombre__iexact=quien_entrega)
                    .order_by("id")
                    .first()
                )

                next_legacy = (
                    RecursoAlmacenMovimiento.objects.aggregate(m=Max("legacy_id_movimiento")).get("m") or 300000
                ) + 1

                obs = quien_entrega
                if observaciones_extra:
                    obs = f"{quien_entrega} · {observaciones_extra}"

                legacy_cod_obra = None
                if getattr(almacen, "obra_id", None) and hasattr(almacen.obra, "legacy_cod_obra"):
                    legacy_cod_obra = almacen.obra.legacy_cod_obra

                mov = RecursoAlmacenMovimiento.objects.create(
                    team_id=almacen.team_id,
                    legacy_id_movimiento=next_legacy,
                    almacen=almacen,
                    recurso=recurso,
                    obra=almacen.obra,
                    empleado=empleado,
                    legacy_id_almacen=almacen.legacy_id_almacen,
                    legacy_cod_recurso=167,
                    legacy_cod_obra=legacy_cod_obra,
                    legacy_cod_vivienda="0",
                    unidad="LTRS",
                    cantidad=cantidad,
                    quedan=nuevo_stock,
                    fecha_movimiento=fecha_movimiento,
                    hora_movimiento=hora_movimiento,
                    tipo_movimiento="SALIDA",
                    tipo_movimiento_raw="SALIDA",
                    en_partida=False,
                    vehiculo=vehiculo,
                    kilometraje=kilometraje,
                    observaciones=obs,
                    raw_data={
                        "ui": "gasoil_salida_vehiculo",
                        "origen": "obra_movil_gasoil",
                        "created_from": "obra_movil.gasoil_salida_vehiculo",
                        "mobile_phase": "gas_ux1a",
                        "stock_policy": "SALIDA GASOIL resta stock",
                        "stock_anterior": str(stock_anterior),
                        "stock_nuevo": str(nuevo_stock),
                        "unidad_forzada": "LTRS",
                        "tipo_movimiento_forzado": "SALIDA",
                        "destino_operativo": {
                            "tipo": "VEHICULO",
                            "vehiculo": vehiculo,
                            "kilometraje": str(kilometraje),
                            "quien_entrega": quien_entrega,
                        },
                        "CodRecurso": 167,
                        "IdAlmacen": almacen.legacy_id_almacen,
                        "Vehiculo": vehiculo,
                        "Kilometraje": str(kilometraje),
                        "QuienEntrega": quien_entrega,
                        "created_at": timezone.now().isoformat(),
                        "created_by_user_id": request.user.id if getattr(request, "user", None) and request.user.is_authenticated else None,
                    },
                )

                recurso.stock = nuevo_stock
                recurso.control_stock = True
                recurso.unidad = "LTRS"
                recurso.save(update_fields=["stock", "control_stock", "unidad", "actualizado_en"])

                messages.success(
                    request,
                    f"SALIDA GASOIL registrada. #{mov.legacy_id_movimiento} · {cantidad} LTRS · quedan {nuevo_stock} LTRS."
                )
                return redirect("obra_movil:gasoil_salida_vehiculo")

        except Exception as exc:
            messages.error(request, str(exc))

    context = _dashboard_context(request)
    context.update({
        "page_title": "Salida GASOIL vehículo",
        "recurso": recurso,
        "almacen": almacen,
        "stock_actual": recurso.stock if recurso else None,
        "error_base": error_base,
        "form_values": form_values,
        "vehiculos": vehiculos,
        "entregadores": recargadores_final,
        "gas_ux1a_marker": "GAS_UX1A_SALIDA_VEHICULO_OK",
    })
    return render(request, "obra_movil/gasoil_salida_vehiculo.html", context)

# =============================================================================
# GAS UX 1C · Redirecciones definitivas GASOIL
# =============================================================================
@login_required
def gasoil_home(request):
    # GAS_UX1C_HOME_REDIRECT_OK
    from django.shortcuts import redirect
    return redirect("obra_movil:gasoil_salida_vehiculo")


@login_required
def gasoil_nuevo(request):
    # GAS_UX1C_NUEVO_REDIRECT_OK
    from django.shortcuts import redirect
    return redirect("obra_movil:gasoil_salida_vehiculo")

# =============================================================================
# STOCK UX 1A · Stock rápido materiales críticos
# =============================================================================
@login_required
def stock_rapido(request):
    # STOCK_UX1A_RAPIDO_OK
    from django.shortcuts import render
    from django.db.models import Q
    from planificacion_obra.models import RecursoCatalogo, RecursoAlmacenMovimiento

    legacy_ids = [167, 383, 1547]
    q = (request.GET.get("q") or "").strip()

    recursos_qs = RecursoCatalogo.objects.filter(legacy_id__in=legacy_ids)

    if q:
        recursos_qs = RecursoCatalogo.objects.filter(
            Q(nombre__icontains=q) |
            Q(legacy_id__icontains=q)
        ).filter(tipo="MATERIAL").order_by("nombre")[:25]
    else:
        recursos_qs = recursos_qs.order_by("legacy_id", "nombre")

    cards = []
    for r in recursos_qs:
        movs = list(
            RecursoAlmacenMovimiento.objects
            .filter(recurso_id=r.id)
            .select_related("almacen")
            .order_by("-fecha_movimiento", "-hora_movimiento", "-id")[:8]
        )

        ultimo = movs[0] if movs else None
        stock_catalogo = r.stock
        ultimo_quedan = ultimo.quedan if ultimo else None

        alerta_stock = False
        try:
            if stock_catalogo is not None and ultimo_quedan is not None:
                alerta_stock = abs(stock_catalogo - ultimo_quedan) > 0.001
        except Exception:
            alerta_stock = False

        accion_url = "/app/obra-movil/almacen/rapido/?q_recurso=%s" % r.legacy_id
        if r.legacy_id == 167:
            accion_url = "/app/obra-movil/gasoil/salida/"

        cards.append({
            "recurso": r,
            "movimientos": movs,
            "ultimo": ultimo,
            "stock_catalogo": stock_catalogo,
            "ultimo_quedan": ultimo_quedan,
            "alerta_stock": alerta_stock,
            "accion_url": accion_url,
        })

    context = {
        "page_title": "Stock rápido",
        "cards": cards,
        "q": q,
        "stock_ux1a_marker": "STOCK_UX1A_RAPIDO_OK",
    }
    return render(request, "obra_movil/stock_rapido.html", context)

# =============================================================================
# ALM MOV UX 1A · Editar / eliminar movimientos de almacén
# =============================================================================
def _alm_mov_ux1a_decimal(value, field_label="valor", required=True):
    from decimal import Decimal, InvalidOperation

    raw = str(value or "").strip().replace(" ", "")
    if not raw:
        if required:
            raise ValueError(f"{field_label} es obligatorio.")
        return None

    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")

    try:
        return Decimal(raw)
    except InvalidOperation:
        raise ValueError(f"{field_label} no es válido.")


def _alm_mov_ux1a_refresh_recurso_stock(recurso, almacen=None):
    if not recurso:
        return None

    from planificacion_obra.models import RecursoAlmacenMovimiento

    qs = RecursoAlmacenMovimiento.objects.filter(
        recurso_id=recurso.pk,
        quedan__isnull=False,
    )
    if almacen:
        qs = qs.filter(almacen_id=almacen.pk)

    ultimo = qs.order_by("-fecha_movimiento", "-hora_movimiento", "-id").first()
    if ultimo and getattr(recurso, "control_stock", False):
        recurso.stock = ultimo.quedan
        recurso.unidad = recurso.unidad or ultimo.unidad or ""
        recurso.save(update_fields=["stock", "unidad", "actualizado_en"])
    return ultimo


def _alm_mov_ux1a_base_qs(request):
    from planificacion_obra.models import RecursoAlmacenMovimiento

    qs = RecursoAlmacenMovimiento.objects.select_related(
        "team",
        "almacen",
        "almacen__obra",
        "obra",
        "unidad_obra",
        "partida",
        "empleado",
        "recurso",
    )
    return _alm_ux3_apply_team_scope(qs, request)


@_alm_ux3_login_required
def _legacy_almacen_movimiento_editar(request, pk):
    # ALM_MOV_UX1A_EDIT_OK
    from datetime import datetime
    from django.contrib import messages
    from django.db import transaction
    from django.shortcuts import get_object_or_404, redirect, render
    from django.urls import reverse
    from django.utils import timezone

    from planificacion_obra.models import (
        AlmacenObra,
        RecursoAlmacenMovimiento,
        RecursoCatalogo,
        TareaRecursoReal,
    )

    mov = get_object_or_404(_alm_mov_ux1a_base_qs(request), pk=pk)
    tiene_real = TareaRecursoReal.objects.filter(movimiento_almacen_id=mov.pk).exists()

    scope_movs = _alm_ux3_apply_team_scope(RecursoAlmacenMovimiento.objects.all(), request)
    scope_team_ids = list(scope_movs.values_list("team_id", flat=True).distinct())

    almacenes = AlmacenObra.objects.filter(team_id__in=scope_team_ids).select_related("obra").order_by("obra__legacy_cod_obra", "nombre", "id")
    recursos = RecursoCatalogo.objects.filter(team_id__in=scope_team_ids).order_by("legacy_id", "nombre")[:5000]

    def _initial():
        return {
            "fecha_movimiento": str(mov.fecha_movimiento or timezone.localdate()),
            "hora_movimiento": (mov.hora_movimiento.strftime("%H:%M") if mov.hora_movimiento else ""),
            "tipo_movimiento": mov.tipo_movimiento or "SALIDA",
            "almacen": str(mov.almacen_id or ""),
            "recurso": str(mov.recurso_id or ""),
            "cantidad": str(mov.cantidad or ""),
            "unidad": mov.unidad or "",
            "quedan": str(mov.quedan or ""),
            "vehiculo": mov.vehiculo or "",
            "kilometraje": str(mov.kilometraje or ""),
            "cod_albaran": mov.cod_albaran or "",
            "observaciones": mov.observaciones or "",
        }

    form_values = _initial()
    if request.method == "POST":
        form_values = {k: (request.POST.get(k) or "").strip() for k in form_values.keys()}

        try:
            with transaction.atomic():
                mov_locked = RecursoAlmacenMovimiento.objects.select_for_update().get(pk=mov.pk)

                old_recurso = mov_locked.recurso
                old_almacen = mov_locked.almacen

                fecha = datetime.strptime(form_values["fecha_movimiento"], "%Y-%m-%d").date()
                hora = None
                if form_values["hora_movimiento"]:
                    hora = datetime.strptime(form_values["hora_movimiento"], "%H:%M").time()

                cantidad = _alm_mov_ux1a_decimal(form_values["cantidad"], "Cantidad")
                quedan = _alm_mov_ux1a_decimal(form_values["quedan"], "Quedan", required=False)
                kilometraje = _alm_mov_ux1a_decimal(form_values["kilometraje"], "Kilometraje", required=False)

                tipo_movimiento = form_values["tipo_movimiento"].upper()
                if tipo_movimiento not in {"ENTRADA", "SALIDA", "CONTROL_STOCK", "ROTURA"}:
                    raise ValueError("Tipo de movimiento no válido.")

                almacen = AlmacenObra.objects.filter(pk=form_values["almacen"]).first() if form_values["almacen"] else None
                recurso = RecursoCatalogo.objects.filter(pk=form_values["recurso"]).first() if form_values["recurso"] else None

                if not recurso:
                    raise ValueError("Recurso obligatorio.")

                cambios_clave = (
                    str(mov_locked.recurso_id or "") != str(recurso.pk)
                    or str(mov_locked.almacen_id or "") != str(almacen.pk if almacen else "")
                    or str(mov_locked.tipo_movimiento or "") != tipo_movimiento
                    or str(mov_locked.cantidad or "") != str(cantidad)
                    or str(mov_locked.quedan or "") != str(quedan)
                )

                if tiene_real and cambios_clave:
                    raise ValueError("Este movimiento ya está imputado a planificación. Solo puedes editar observaciones, vehículo, km, fecha/hora o albarán.")

                raw = mov_locked.raw_data if isinstance(mov_locked.raw_data, dict) else {}
                raw = dict(raw)
                raw.setdefault("_ediciones", [])
                raw["_ediciones"].append({
                    "marker": "ALM_MOV_UX1A_EDIT_OK",
                    "updated_at": timezone.now().isoformat(),
                    "updated_by_user_id": getattr(request.user, "pk", None),
                })

                mov_locked.fecha_movimiento = fecha
                mov_locked.hora_movimiento = hora
                mov_locked.tipo_movimiento = tipo_movimiento
                mov_locked.tipo_movimiento_raw = tipo_movimiento
                mov_locked.almacen = almacen
                mov_locked.recurso = recurso
                mov_locked.obra = getattr(almacen, "obra", None) or mov_locked.obra
                mov_locked.legacy_id_almacen = getattr(almacen, "legacy_id_almacen", "") if almacen else ""
                mov_locked.legacy_cod_recurso = getattr(recurso, "legacy_id", None)
                mov_locked.cantidad = cantidad
                mov_locked.unidad = form_values["unidad"] or getattr(recurso, "unidad", "") or mov_locked.unidad
                mov_locked.quedan = quedan
                mov_locked.vehiculo = form_values["vehiculo"].upper()
                mov_locked.kilometraje = kilometraje
                mov_locked.cod_albaran = form_values["cod_albaran"]
                mov_locked.observaciones = form_values["observaciones"]
                mov_locked.raw_data = raw

                mov_locked.save(update_fields=[
                    "fecha_movimiento",
                    "hora_movimiento",
                    "tipo_movimiento",
                    "tipo_movimiento_raw",
                    "almacen",
                    "recurso",
                    "obra",
                    "legacy_id_almacen",
                    "legacy_cod_recurso",
                    "cantidad",
                    "unidad",
                    "quedan",
                    "vehiculo",
                    "kilometraje",
                    "cod_albaran",
                    "observaciones",
                    "raw_data",
                    "updated_at",
                ])

                _alm_mov_ux1a_refresh_recurso_stock(old_recurso, old_almacen)
                _alm_mov_ux1a_refresh_recurso_stock(recurso, almacen)

                messages.success(request, f"Movimiento #{mov_locked.legacy_id_movimiento or mov_locked.pk} actualizado.")
                return redirect(f"{reverse('obra_movil:almacen_movimientos')}?q={mov_locked.pk}")

        except Exception as exc:
            messages.error(request, str(exc))

    context = {}
    try:
        context.update(_dashboard_context(request))
    except Exception:
        pass

    context.update({
        "alm_mov_ux1a_marker": "ALM_MOV_UX1A_EDIT_OK",
        "mov": mov,
        "form_values": form_values,
        "almacenes": almacenes,
        "recursos": recursos,
        "tipos": ["ENTRADA", "SALIDA", "CONTROL_STOCK", "ROTURA"],
        "tiene_real": tiene_real,
    })
    return render(request, "obra_movil/almacen_movimiento_editar.html", context)


@_alm_ux3_login_required
def _legacy_almacen_movimiento_eliminar(request, pk):
    # ALM_MOV_UX1A_DELETE_OK
    from django.contrib import messages
    from django.db import transaction
    from django.shortcuts import get_object_or_404, redirect, render

    from planificacion_obra.models import TareaRecursoReal

    mov = get_object_or_404(_alm_mov_ux1a_base_qs(request), pk=pk)
    tiene_real = TareaRecursoReal.objects.filter(movimiento_almacen_id=mov.pk).exists()

    if request.method == "POST":
        try:
            with transaction.atomic():
                # ALM_MOV_UX1A_DELETE_SELECT_FOR_UPDATE_FIX_OK
                # Bloquear solo la fila base. No usar select_related + select_for_update:
                # PostgreSQL falla con joins nullable.
                from planificacion_obra.models import RecursoAlmacenMovimiento

                allowed = _alm_mov_ux1a_base_qs(request).filter(pk=pk).exists()
                if not allowed:
                    raise ValueError("Movimiento no encontrado o sin permiso.")

                mov_locked = RecursoAlmacenMovimiento.objects.select_for_update().get(pk=pk)

                if TareaRecursoReal.objects.filter(movimiento_almacen_id=mov_locked.pk).exists():
                    raise ValueError("No se puede eliminar: este movimiento tiene recurso real vinculado en planificación.")

                legacy = mov_locked.legacy_id_movimiento or mov_locked.pk
                recurso = mov_locked.recurso
                almacen = mov_locked.almacen

                mov_locked.delete()
                _alm_mov_ux1a_refresh_recurso_stock(recurso, almacen)

                messages.success(request, f"Movimiento #{legacy} eliminado.")
                return redirect("obra_movil:almacen_movimientos")

        except Exception as exc:
            messages.error(request, str(exc))
            return redirect("obra_movil:almacen_movimientos")

    context = {}
    try:
        context.update(_dashboard_context(request))
    except Exception:
        pass

    context.update({
        "alm_mov_ux1a_marker": "ALM_MOV_UX1A_DELETE_OK",
        "mov": mov,
        "tiene_real": tiene_real,
    })
    return render(request, "obra_movil/almacen_movimiento_eliminar.html", context)


# MOVIMIENTOS_ALMACEN_EDIT_DELETE_V1
# Definiciones finales deliberadamente al final del módulo para sustituir las
# rutas legacy sin alterar otros flujos de Obra móvil.
@_alm_ux3_login_required
def almacen_movimiento_editar(request, pk):
    from datetime import datetime
    from decimal import Decimal, InvalidOperation
    from django.core.exceptions import PermissionDenied
    from django.contrib import messages
    from django.shortcuts import get_object_or_404, redirect, render
    from django.urls import reverse
    from .movimientos_almacen import (
        classify_movement, origin_label, permission_allowed, update_manual_movement,
    )

    mov = get_object_or_404(_alm_mov_ux1a_base_qs(request), pk=pk)
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if not next_url.startswith("/app/"):
        next_url = ""
    origin = classify_movement(mov)
    blocked_reason = "" if origin == "MANUAL" else f"Bloqueado: {origin_label(origin)}. Debe corregirse desde su origen o mediante una reversión."
    if origin == "MANUAL" and not permission_allowed(request.user, "planificacion_obra.change_recursoalmacenmovimiento"):
        raise PermissionDenied("No tienes permiso para editar movimientos de almacén.")

    form_values = {
        "fecha_movimiento": mov.fecha_movimiento.isoformat() if mov.fecha_movimiento else "",
        "hora_movimiento": mov.hora_movimiento.strftime("%H:%M") if mov.hora_movimiento else "",
        "cantidad": str(mov.cantidad or ""),
        "observaciones": mov.observaciones or "",
    }
    if request.method == "POST":
        structural = {"recurso", "almacen", "tipo_movimiento", "team", "partida", "cod_albaran", "cod_factura", "en_partida"}
        if structural.intersection(request.POST):
            messages.error(request, "No se pueden modificar campos estructurales desde esta pantalla.")
        else:
            try:
                form_values = {key: (request.POST.get(key) or "").strip() for key in form_values}
                fecha = datetime.strptime(form_values["fecha_movimiento"], "%Y-%m-%d").date()
                hora = datetime.strptime(form_values["hora_movimiento"], "%H:%M").time() if form_values["hora_movimiento"] else None
                cantidad_raw = form_values["cantidad"].replace(" ", "").replace(",", ".")
                cantidad = Decimal(cantidad_raw)
                if cantidad < 0:
                    raise ValueError("La cantidad no puede ser negativa.")
                update_manual_movement(
                    movement_id=mov.pk,
                    user=request.user,
                    values={"cantidad": cantidad, "fecha_movimiento": fecha, "hora_movimiento": hora, "observaciones": form_values["observaciones"]},
                )
                messages.success(request, f"Movimiento #{mov.legacy_id_movimiento or mov.pk} actualizado y stock recalculado.")
                return redirect(next_url or f"{reverse('obra_movil:almacen_movimientos')}?q={mov.pk}")
            except (InvalidOperation, ValueError, PermissionError) as exc:
                messages.error(request, str(exc))

    return render(request, "obra_movil/almacen_movimiento_editar.html", {
        "mov": mov,
        "form_values": form_values,
        "origin_label": origin_label(origin),
        "blocked_reason": blocked_reason,
        "can_edit": origin == "MANUAL" and permission_allowed(request.user, "planificacion_obra.change_recursoalmacenmovimiento"),
        "next_url": next_url,
    })


@_alm_ux3_login_required
def almacen_movimiento_eliminar(request, pk):
    from django.contrib import messages
    from django.core.exceptions import PermissionDenied
    from django.shortcuts import get_object_or_404, redirect, render
    from .movimientos_almacen import (
        classify_movement, delete_manual_movement, origin_label, permission_allowed,
    )

    mov = get_object_or_404(_alm_mov_ux1a_base_qs(request), pk=pk)
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if not next_url.startswith("/app/"):
        next_url = ""
    origin = classify_movement(mov)
    blocked_reason = "" if origin == "MANUAL" else f"Bloqueado: {origin_label(origin)}. Debe corregirse desde su origen o mediante una reversión."
    if origin == "MANUAL" and not permission_allowed(request.user, "planificacion_obra.delete_recursoalmacenmovimiento"):
        raise PermissionDenied("No tienes permiso para eliminar movimientos de almacén.")
    if request.method == "POST":
        try:
            before, _stock_after = delete_manual_movement(movement_id=mov.pk, user=request.user)
            messages.success(request, f"Movimiento #{before['legacy_id_movimiento'] or before['id']} eliminado y stock recalculado.")
            return redirect(next_url or "obra_movil:almacen_movimientos")
        except (ValueError, PermissionError) as exc:
            messages.error(request, str(exc))
    return render(request, "obra_movil/almacen_movimiento_eliminar.html", {
        "mov": mov,
        "origin_label": origin_label(origin),
        "blocked_reason": blocked_reason,
        "can_delete": origin == "MANUAL" and permission_allowed(request.user, "planificacion_obra.delete_recursoalmacenmovimiento"),
        "next_url": next_url,
    })
