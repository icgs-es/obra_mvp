import csv
import io
from io import BytesIO
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_date
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.core.exceptions import ValidationError
from django.utils.timezone import localtime
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required

from .models import Fichaje, Ausencia, TerminalFichaje
from .forms import AusenciaForm
from .utils import reverse_geocode
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

def _get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip

@login_required
def mi_jornada(request):
    """
    Vista principal móvil / portal de fichajes.
    Muestra resumen del día + lista de fichajes de hoy.
    """
    user = request.user
    hoy = timezone.localdate()

    horas_hoy, fichajes_hoy, estado = Fichaje.calcular_resumen_dia(
        user,
        fecha=hoy,
    )

    # --- Horas semana / mes (de momento placeholders) ---
    horas_semana = None
    horas_mes = None
    
    # ¿Jornada larga? (más de 9 horas hoy)
    jornada_larga = False
    if horas_hoy is not None:
        try:
            jornada_larga = float(horas_hoy) >= 9.0
        except (TypeError, ValueError):
            jornada_larga = False

    # Último PAUSA_IN de hoy (para el contador de pausa)
    ultima_pausa_in = (
        Fichaje.objects
        .filter(user=user, timestamp__date=hoy, tipo="PAUSA_IN")
        .order_by("timestamp")
        .last()
    )

    # Último OTRO_IN de hoy (permiso corto)
    ultimo_permiso_in = (
        Fichaje.objects
        .filter(user=user, timestamp__date=hoy, tipo="OTRO_IN")
        .order_by("timestamp")
        .last()
    )

    permiso_in_ms = None
    if ultimo_permiso_in:
        dt_local_permiso = localtime(ultimo_permiso_in.timestamp)
        permiso_in_ms = int(dt_local_permiso.timestamp() * 1000)

    pausa_in_ms = None
    if ultima_pausa_in:
        dt_local = localtime(ultima_pausa_in.timestamp)
        pausa_in_ms = int(dt_local.timestamp() * 1000)

    # --- Inicio de jornada actual (para contador en vivo) ---
    jornada_in_ms = None
    if estado in ("dentro", "pausa", "permiso"):
        ultimo_in = (
            Fichaje.objects
            .filter(user=user, timestamp__date=hoy, tipo="IN")
            .order_by("timestamp")
            .last()
        )
        if ultimo_in:
            dt_local_in = localtime(ultimo_in.timestamp)
            jornada_in_ms = int(dt_local_in.timestamp() * 1000)

    # 🔹 Último fichaje de hoy (para mostrar lugar actual)
    ultimo_fichaje = fichajes_hoy.last() if fichajes_hoy else None
    ultimo_lugar = None
    ultimo_maps = None

    if ultimo_fichaje:
        if ultimo_fichaje.short_location:
            ultimo_lugar = ultimo_fichaje.short_location
        if ultimo_fichaje.maps_url:
            ultimo_maps = ultimo_fichaje.maps_url

    context = {
        "hoy": hoy,
        "horas_hoy": horas_hoy,
        "fichajes_hoy": fichajes_hoy,
        "estado": estado,
        "pausa_in_ms": pausa_in_ms,
        "permiso_in_ms": permiso_in_ms,
        "horas_semana": horas_semana,
        "horas_mes": horas_mes,
        "ultimo_lugar": ultimo_lugar,      # 👈 NUEVO
        "ultimo_maps": ultimo_maps,        # 👈 NUEVO
        "jornada_larga": jornada_larga,     # 👈 NUEVO
        "jornada_in_ms": jornada_in_ms,   # 👈 NUEVO
    }
    return render(request, "fichajes/mi_jornada.html", context)

def validar_nuevo_fichaje(usuario, tipo):
    """
    Reglas de negocio para un nuevo fichaje.

    Devuelve (ok: bool, mensaje_error: str).
    Solo tiene en cuenta fichajes de HOY.
    """
    hoy = timezone.localdate()

    # último fichaje de hoy
    ultimo = (
        Fichaje.objects
        .filter(user=usuario, timestamp__date=hoy)
        .order_by("-timestamp")
        .first()
    )

    # ---- Reglas por tipo ----

    # ENTRADA
    if tipo == "IN":
        if ultimo and ultimo.tipo in ("IN", "PAUSA_IN", "OTRO_IN"):
            return False, "Ya estás dentro de la jornada. Debes fichar salida antes de volver a entrar."
        return True, ""

    # SALIDA
    if tipo == "OUT":
        if not ultimo or ultimo.tipo == "OUT":
            return False, "No tienes una entrada activa hoy. No puedes fichar salida."
        if ultimo.tipo in ("PAUSA_IN", "OTRO_IN"):
            return False, "Tienes una pausa o un permiso corto abierto. Ciérralo antes de fichar salida."
        return True, ""

    # INICIO PAUSA
    if tipo == "PAUSA_IN":
        if not ultimo or ultimo.tipo == "OUT":
            return False, "No puedes iniciar una pausa si no has fichado entrada."
        if ultimo.tipo == "PAUSA_IN":
            return False, "Ya tienes una pausa iniciada."
        if ultimo.tipo == "OTRO_IN":
            return False, "No puedes iniciar una pausa mientras estás en un permiso corto."
        return True, ""

    # FIN PAUSA
    if tipo == "PAUSA_OUT":
        if not ultimo or ultimo.tipo != "PAUSA_IN":
            return False, "No tienes ninguna pausa abierta."
        return True, ""

    # INICIO PERMISO CORTO
    if tipo == "OTRO_IN":
        if not ultimo or ultimo.tipo == "OUT":
            return False, "No puedes iniciar un permiso corto si no has fichado entrada."
        if ultimo.tipo == "OTRO_IN":
            return False, "Ya tienes un permiso corto iniciado."
        if ultimo.tipo == "PAUSA_IN":
            return False, "No puedes iniciar un permiso corto mientras estás en pausa."
        return True, ""

    # FIN PERMISO CORTO
    if tipo == "OTRO_OUT":
        if not ultimo or ultimo.tipo != "OTRO_IN":
            return False, "No tienes ningún permiso corto abierto."
        return True, ""

    # Tipo desconocido
    return False, "Tipo de fichaje no reconocido."

@login_required
@require_POST
def fichar(request):
    """
    Registra un fichaje:
      - Si viene 'tipo' en POST: IN / OUT / PAUSA_IN / PAUSA_OUT / OTRO_IN / OTRO_OUT
      - Si NO viene 'tipo': comportamiento antiguo toggle IN/OUT
    """
    user = request.user
    ahora = timezone.now()

    lat = request.POST.get("lat") or None
    lng = request.POST.get("lng") or None
    tipo = request.POST.get("tipo")  # puede venir del botón

    # Último fichaje del usuario (para el modo "toggle" antiguo)
    ultimo = (
        Fichaje.objects
        .filter(user=user)
        .order_by("-timestamp")
        .first()
    )

    # 1) Si viene un tipo explícito desde el formulario, lo validamos
    if tipo:
        ok, error_msg = validar_nuevo_fichaje(user, tipo)
        if not ok:
            messages.error(request, error_msg)
            return redirect("fichajes:mi_jornada")

                # ⚙️ Creamos el fichaje normalmente
        f = Fichaje.objects.create(
            user=user,
            tipo=tipo,
            timestamp=ahora,
            lat=lat,
            lng=lng,
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
            origen="PORTAL",
        )

        # 🌍 Intentar obtener texto de ubicación SI tenemos coordenadas
        if f.lat and f.lng and f.location_text is None:
            try:
                f.location_text = reverse_geocode(f.lat, f.lng)
                f.save(update_fields=["location_text"])
            except Exception as e:
                logger.warning("Reverse geocoding falló: %s", e)

        # Mensaje bonito usando las labels de choices
        label_dict = dict(Fichaje.TIPO_CHOICES)
        label = label_dict.get(tipo, tipo)
        messages.success(request, f"Fichaje registrado: {label}.")
        return redirect("fichajes:mi_jornada")

    # 2) Compatibilidad: sin tipo → alternar IN / OUT como antes
    if ultimo and ultimo.tipo == "IN":
        nuevo_tipo = "OUT"
        msg = "Salida fichada correctamente."
    else:
        nuevo_tipo = "IN"
        msg = "Entrada fichada correctamente."

    # ⚙️ Creamos el fichaje
    f = Fichaje.objects.create(
        user=user,
        tipo=nuevo_tipo,
        timestamp=ahora,
        lat=lat,
        lng=lng,
        ip=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
        origen="PORTAL",
    )

    # 🌍 Intentar obtener texto de ubicación
    if f.lat and f.lng and f.location_text is None:
        try:
            f.location_text = reverse_geocode(f.lat, f.lng)
            f.save(update_fields=["location_text"])
        except Exception as e:
            logger.warning("Reverse geocoding falló: %s", e)

    messages.success(request, msg)
    return redirect("fichajes:mi_jornada")


@login_required
def mis_fichajes(request):
    """
    Listado simple de todos los fichajes del usuario.
    Después haremos filtros por rango de fechas, etc.
    """
    fichajes = Fichaje.objects.filter(user=request.user).order_by("-timestamp")[:200]
    return render(request, "fichajes/listado_fichajes.html", {"fichajes": fichajes})

@login_required
def informe_control_horario(request):
    """
    Informe por usuario y rango de fechas:
    - Si el usuario NO es staff: solo ve su propio informe.
    - Si es staff: puede elegir cualquier usuario.
    """
    hoy = timezone.localdate()

    # --- Rango de fechas: GET ?inicio=YYYY-MM-DD&fin=YYYY-MM-DD
    inicio_str = request.GET.get("inicio")
    fin_str = request.GET.get("fin")

    if inicio_str:
        inicio = parse_date(inicio_str)
    else:
        # Por defecto: primer día del mes actual
        inicio = hoy.replace(day=1)

    if fin_str:
        fin = parse_date(fin_str)
    else:
        fin = hoy

    if inicio is None:
        inicio = hoy.replace(day=1)
    if fin is None:
        fin = hoy

    if fin < inicio:
        fin = inicio

    # --- Selección de usuario
    user_id = request.GET.get("user_id")
    if request.user.is_staff and user_id:
        try:
            empleado = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            empleado = request.user
    else:
        empleado = request.user

    # --- Recorrer días y calcular horas
    dias = []
    total_horas = 0.0

    current = inicio
    while current <= fin:
        horas, fichajes_dia, estado = Fichaje.calcular_resumen_dia(empleado, current)
        dias.append({
            "fecha": current,
            "horas": horas,
            "fichajes": fichajes_dia,
            "estado": estado,
        })
        total_horas += horas
        current += timedelta(days=1)

    # --- Lista de usuarios para selector (solo staff)
    empleados = []
    if request.user.is_staff:
        empleados = User.objects.order_by("first_name", "last_name", "username")

    context = {
        "empleado": empleado,
        "empleados": empleados,
        "inicio": inicio,
        "fin": fin,
        "dias": dias,
        "total_horas": total_horas,
    }
    return render(request, "fichajes/informe_control_horario.html", context)

@login_required
def informe_control_horario_csv(request):
    """
    Exporta a CSV todos los fichajes de un usuario en un rango de fechas.
    Formato pensado para inspección / gestoría.
    """
    hoy = timezone.localdate()

    # --- Rango de fechas
    inicio_str = request.GET.get("inicio")
    fin_str = request.GET.get("fin")

    if inicio_str:
        inicio = parse_date(inicio_str)
    else:
        inicio = hoy.replace(day=1)

    if fin_str:
        fin = parse_date(fin_str)
    else:
        fin = hoy

    if inicio is None:
        inicio = hoy.replace(day=1)
    if fin is None:
        fin = hoy
    if fin < inicio:
        fin = inicio

    # --- Usuario
    user_id = request.GET.get("user_id")
    if request.user.is_staff and user_id:
        try:
            empleado = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            empleado = request.user
    else:
        empleado = request.user

    # --- Query de fichajes
    fichajes = (
        Fichaje.objects
        .filter(
            user=empleado,
            timestamp__date__gte=inicio,
            timestamp__date__lte=fin,
        )
        .order_by("timestamp")
    )

    # --- Preparar respuesta CSV
    filename = f"control_horario_{empleado.username}_{inicio}_{fin}.csv"
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response, delimiter=";")

    # Cabecera
    writer.writerow([
        "Empleado",
        "Fecha",
        "Hora",
        "Tipo",
        "IP",
        "Latitud",
        "Longitud",
        "Observaciones",
    ])

    # Filas
    for f in fichajes:
        writer.writerow([
            empleado.get_full_name() or empleado.username,
            f.timestamp.date().isoformat(),
            f.timestamp.time().strftime("%H:%M:%S"),
            f.get_tipo_display(),
            f.ip or "",
            f.lat or "",
            f.lng or "",
            (f.observaciones or "").replace("\n", " ").strip(),
        ])

    return response

@login_required
def ausencias_list(request):
    ausencias, filtros = _get_ausencias_filtradas(request)

    # Choices para los selects
    estado_choices = Ausencia.ESTADO_CHOICES
    tipo_choices = Ausencia.TIPO_CHOICES

    empleados = User.objects.filter(ausencias__isnull=False).distinct().order_by(
        "first_name",
        "last_name",
        "username",
    )

    context = {
        "ausencias": ausencias,
        "filtros": filtros,
        "estado_choices": estado_choices,
        "tipo_choices": tipo_choices,
        "empleados": empleados,
    }
    return render(request, "fichajes/ausencias_list.html", context)

@login_required
def ausencia_create(request):
    initial = {}

    # soportar fechas desde el calendario
    fi = request.GET.get("fecha_inicio")
    ff = request.GET.get("fecha_fin")
    if fi:
        initial["fecha_inicio"] = fi
    if ff:
        initial["fecha_fin"] = ff

    if request.method == "POST":
        form = AusenciaForm(request.POST)
        if form.is_valid():
            ausencia = form.save(commit=False)
            ausencia.empleado = request.user              # 🔥 empleado SIEMPRE es el usuario actual
            ausencia.creado_por = request.user            # 🔥 creador
            ausencia.save()
            messages.success(request, "Ausencia guardada correctamente.")
            return redirect("fichajes:ausencias_list")
    else:
        form = AusenciaForm(initial=initial)

    return render(
        request,
        "fichajes/ausencia_form.html",
        {"form": form, "modo": "crear", "ausencia": None},
    )

@login_required
def ausencia_edit(request, pk):
    ausencia = get_object_or_404(Ausencia, pk=pk)

    if not request.user.is_staff and ausencia.empleado != request.user:
        return HttpResponseForbidden("No tienes permiso para editar esta ausencia.")

    if request.method == "POST":
        form = AusenciaForm(request.POST, instance=ausencia)
        if form.is_valid():
            form.save()
            messages.success(request, "Ausencia actualizada.")
            return redirect("fichajes:ausencias_list")
    else:
        form = AusenciaForm(instance=ausencia)

    return render(
        request,
        "fichajes/ausencia_form.html",
        {"form": form, "ausencia": ausencia, "modo": "editar"},
    )

@login_required
def informe_ausencias_empleado_pdf(request, user_id=None):
    # Si no se indica empleado, usamos el usuario logado
    if user_id:
        empleado = get_object_or_404(User, pk=user_id)
    else:
        empleado = request.user

    ausencias = Ausencia.objects.filter(empleado=empleado).order_by("-fecha_inicio")

    template = get_template("fichajes/informe_ausencias_pdf.html")
    html = template.render(
        {
            "empleado": empleado,
            "ausencias": ausencias,
            "request": request,
        }
    )

    result = io.BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=result, encoding="UTF-8")

    if pisa_status.err:
        return HttpResponse("Error generando el PDF", status=500)

    response = HttpResponse(result.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="ausencias_{empleado.username}.pdf"'
    )
    return response

@login_required
def informe_ausencias_csv(request):
    # aquí puedes filtrar por fechas/empleado si lo necesitas
    #ausencias = (
    #    Ausencia.objects.select_related("empleado")
    #    .order_by("-fecha_inicio", "-fecha_fin")
    #)
    ausencias, filtros = _get_ausencias_filtradas(request)
    
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="ausencias_intasa.csv"'

    writer = csv.writer(response)
    # Cabecera de columnas
    writer.writerow(
        ["Empleado", "Tipo", "Fecha inicio", "Fecha fin", "Estado", "Motivo"]
    )

    for a in ausencias:
        writer.writerow(
            [
                getattr(a.empleado, "get_full_name", lambda: str(a.empleado))(),
                getattr(a, "get_tipo_display", lambda: a.tipo)(),
                a.fecha_inicio,
                a.fecha_fin,
                getattr(a, "get_estado_display", lambda: a.estado)(),
                getattr(a, "motivo", "") or "",
            ]
        )

    return response

@login_required
def informe_ausencias_pdf(request):
    #ausencias = (
    #    Ausencia.objects.select_related("empleado")
    #    .order_by("-fecha_inicio", "-fecha_fin")
    #)
    ausencias, filtros = _get_ausencias_filtradas(request)

    template = get_template("fichajes/informe_ausencias_pdf.html")
    html = template.render(
        {
            "ausencias": ausencias,
            "usuario": request.user,
        }
    )

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="ausencias_intasa.pdf"'

    # Generar el PDF
    pisa_status = pisa.CreatePDF(html, dest=response)

    if pisa_status.err:
        return HttpResponse(
            "Error al generar el PDF de ausencias", status=500
        )

    return response

def _get_ausencias_filtradas(request):
    """
    Devuelve un queryset de Ausencia filtrado según GET (estado, tipo, empleado)
    y un diccionario con los valores de filtro seleccionados.
    """
    qs = Ausencia.objects.all().select_related("empleado")

    # Permisos básicos
    if not request.user.is_staff:
        qs = qs.filter(empleado=request.user)

    estado = request.GET.get("estado") or ""
    tipo = request.GET.get("tipo") or ""
    empleado_id = request.GET.get("empleado") or ""

    if estado:
        qs = qs.filter(estado=estado)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if empleado_id and request.user.is_staff:
        qs = qs.filter(empleado_id=empleado_id)

    filtros = {
        "estado": estado,
        "tipo": tipo,
        "empleado": empleado_id,
    }
    return qs, filtros

@login_required
def informe_fichajes_hoy_pdf(request):
    usuario = request.user
    hoy = timezone.localdate()

    # Fichajes del día, ordenados cronológicamente
    fichajes = (
        Fichaje.objects
        .filter(user=usuario, timestamp__date=hoy)
        .order_by("timestamp")
    )

    # Usamos tu lógica ya existente para calcular horas del día
    horas_hoy, _, _ = Fichaje.calcular_resumen_dia(
        usuario,
        fecha=hoy,
    )

    template = get_template("fichajes/informe_fichajes_hoy_pdf.html")
    html = template.render(
        {
            "usuario": usuario,
            "hoy": hoy,
            "fichajes": fichajes,
            "horas_hoy": horas_hoy,
            "request": request,  # por si lo necesitas para estáticos
        }
    )

    result = io.BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=result, encoding="UTF-8")

    if pisa_status.err:
        return HttpResponse("Error generando el PDF de fichajes", status=500)

    filename = f"fichajes_{usuario.username}_{hoy}.pdf"
    response = HttpResponse(result.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

@login_required
def informe_fichajes_rango_pdf(request, user_id=None):
    """
    Genera un PDF con los fichajes de un usuario en un rango de fechas.

    - Si user_id viene en la URL y el usuario es staff -> se genera para ese empleado.
    - Si NO viene user_id o el usuario no es staff -> se genera para el propio request.user.

    El rango se pasa por GET:
      ?desde=YYYY-MM-DD&hasta=YYYY-MM-DD
    """
    # 1) Determinar el empleado objetivo
    if user_id and request.user.is_staff:
        empleado = get_object_or_404(User, pk=user_id)
    else:
        empleado = request.user

    # 2) Leer fechas del GET
    desde_str = request.GET.get("desde")
    hasta_str = request.GET.get("hasta")

    hoy = timezone.localdate()

    # Si no vienen, por defecto hoy
    if not desde_str:
        desde = hoy
    else:
        try:
            desde = datetime.strptime(desde_str, "%Y-%m-%d").date()
        except ValueError:
            desde = hoy

    if not hasta_str:
        hasta = hoy
    else:
        try:
            hasta = datetime.strptime(hasta_str, "%Y-%m-%d").date()
        except ValueError:
            hasta = hoy

    if hasta < desde:
        # Intercambiamos por si vienen al revés
        desde, hasta = hasta, desde

    # 3) Fichajes del rango
    fichajes = (
        Fichaje.objects
        .filter(
            user=empleado,
            timestamp__date__gte=desde,
            timestamp__date__lte=hasta,
        )
        .order_by("timestamp")
    )

    # 4) Calcular horas totales del rango sumando día a día
    total_horas = 0.0
    fecha_iter = desde
    while fecha_iter <= hasta:
        horas_dia, _, _ = Fichaje.calcular_resumen_dia(empleado, fecha=fecha_iter)
        if horas_dia:
            try:
                total_horas += float(horas_dia)
            except (TypeError, ValueError):
                pass
        fecha_iter += timedelta(days=1)

    # 5) Renderizar plantilla PDF
    template = get_template("fichajes/informe_fichajes_rango_pdf.html")
    html = template.render(
        {
            "empleado": empleado,
            "desde": desde,
            "hasta": hasta,
            "fichajes": fichajes,
            "total_horas": total_horas,
            "request": request,
        }
    )

    result = io.BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=result, encoding="UTF-8")

    if pisa_status.err:
        return HttpResponse("Error generando el PDF de fichajes (rango)", status=500)

    filename = f"fichajes_{empleado.username}_{desde}_{hasta}.pdf"
    response = HttpResponse(result.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

@require_http_methods(["GET", "POST"])
def terminal_fichaje(request):
    """
    Terminal de fichaje para tablet:
    - No requiere login.
    - El empleado introduce su PIN y elige tipo de fichaje.
    - Reutiliza validar_nuevo_fichaje y el modelo Fichaje.
    """
    context = {}

    if request.method == "POST":
        pin = (request.POST.get("pin") or "").strip()
        tipo = request.POST.get("tipo") or ""

        if not pin or not tipo:
            messages.error(request, "Debes introducir tu PIN y elegir el tipo de fichaje.")
            return render(request, "fichajes/terminal_fichaje.html", context)

        # Buscar usuario por PIN
        try:
            terminal = TerminalFichaje.objects.select_related("user").get(
                pin=pin,
                activo=True,
            )
        except TerminalFichaje.DoesNotExist:
            messages.error(request, "PIN no válido o inactivo.")
            return render(request, "fichajes/terminal_fichaje.html", context)

        empleado = terminal.user

        # Reutilizamos tus reglas de negocio
        ok, error_msg = validar_nuevo_fichaje(empleado, tipo)
        if not ok:
            messages.error(request, error_msg)
            return render(request, "fichajes/terminal_fichaje.html", context)

        ahora = timezone.now()

        # Crear fichaje igual que en la vista 'fichar'
        f = Fichaje.objects.create(
            user=empleado,
            tipo=tipo,
            timestamp=ahora,
            lat=None,  # normalmente la tablet fija no dará geolocalización
            lng=None,
            ip=_get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:1000],
            origen="TERMINAL",   # 👈 clave
        )

        label_dict = dict(Fichaje.TIPO_CHOICES)
        label = label_dict.get(tipo, tipo)

        nombre = empleado.get_full_name() or empleado.username
        messages.success(
            request,
            f"Fichaje registrado para {nombre}: {label}.",
        )
        # Volvemos a la pantalla limpia para el siguiente fichaje
        return redirect("fichajes:terminal_fichaje")

    # GET → mostrar formulario vacío
    return render(request, "fichajes/terminal_fichaje.html", context)

@staff_member_required
def terminal_resumen_hoy(request):
    hoy = timezone.localdate()

    # Usuarios que han fichado HOY desde la terminal
    usuarios = (
        User.objects
        .filter(fichajes__timestamp__date=hoy, fichajes__origen="TERMINAL")
        .distinct()
        .order_by("first_name", "last_name", "username")
    )

    filas = []
    for u in usuarios:
        horas_hoy, _, estado = Fichaje.calcular_resumen_dia(u, fecha=hoy)
        ultimo_fichaje = (
            Fichaje.objects
            .filter(user=u, timestamp__date=hoy, origen="TERMINAL")
            .order_by("-timestamp")
            .first()
        )

        filas.append({
            "usuario": u,
            "horas_hoy": horas_hoy,
            "estado": estado,           # 'dentro', 'fuera', 'pausa', 'permiso'
            "ultimo": ultimo_fichaje,
        })

    context = {
        "hoy": hoy,
        "filas": filas,
    }
    return render(request, "fichajes/terminal_resumen_hoy.html", context)
