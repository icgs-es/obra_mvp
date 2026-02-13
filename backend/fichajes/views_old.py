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

from .models import Fichaje, Ausencia
from .forms import AusenciaForm

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
    user = request.user
    hoy = timezone.localdate()

    horas_hoy, fichajes_hoy, estado = Fichaje.calcular_resumen_dia(user, hoy)

    context = {
        "hoy": hoy,
        "horas_hoy": horas_hoy,
        "fichajes_hoy": fichajes_hoy,
        "estado": estado,  # 'dentro' o 'fuera'
    }
    return render(request, "fichajes/mi_jornada.html", context)


@login_required
@require_POST
def fichar(request):
    """
    Acción genérica: si está fuera → Entrada, si está dentro → Salida.
    Luego ya podremos refinar (pausas, etc.)
    """
    user = request.user
    hoy = timezone.localdate()
    _, fichajes_hoy, estado_actual = Fichaje.calcular_resumen_dia(user, hoy)

    # Determinar tipo automático
    tipo = "IN" if estado_actual == "fuera" else "OUT"

    ip = _get_client_ip(request)
    user_agent = request.META.get("HTTP_USER_AGENT", "")[:4000]

    # Geolocalización vendrá por POST (JS)
    lat = request.POST.get("lat")
    lng = request.POST.get("lng")

    Fichaje.objects.create(
        user=user,
        tipo=tipo,
        ip=ip,
        user_agent=user_agent,
        lat=lat or None,
        lng=lng or None,
    )

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