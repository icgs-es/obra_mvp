# backend/fichajes/views_calendar.py

import datetime

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .models import Ausencia

# Colores para cada tipo de ausencia
COLOR_MAP = {
    "VACACIONES": "#4caf50",      # verde
    "PERMISO": "#2196f3",         # azul
    "PERMISO_NR": "#1976d2",      # azul más oscuro
    "BAJA": "#f44336",            # rojo
    "ASUNTOS": "#ff9800",         # naranja
    "FORMACION": "#9c27b0",       # morado
    "OTRA": "#9e9e9e",            # gris
}

# Colores por ESTADO de la ausencia
COLOR_ESTADO = {
    "PENDIENTE": "#ff9800",   # naranja
    "APROBADA": "#4caf50",    # verde
    "RECHAZADA": "#f44336",   # rojo
}

@login_required
def calendario_ausencias(request):
    """
    Vista HTML principal del calendario de ausencias.
    Solo renderiza la plantilla; los datos van por el endpoint JSON.
    """
    return render(request, "fichajes/calendario_ausencias.html", {})


@login_required
@require_GET
def ausencias_events(request):
    """
    Devuelve las ausencias en formato JSON para FullCalendar.
    Parámetros GET:
      - start, end: rango de fechas (ISO8601), los manda FullCalendar.
      - vista: 'mis' | 'departamento' | 'global'
    """
    start = request.GET.get("start")
    end = request.GET.get("end")
    vista = request.GET.get("vista", "mis")

    # --- DEBUG rápido en logs del servidor ---
    print(">>> ausencias_events start=", start, "end=", end, "vista=", vista)

    # Parseo de fechas: FullCalendar envía "YYYY-MM-DDTHH:MM:SSZ"
    try:
        start_date = None
        end_date = None

        if start:
            start_date = datetime.date.fromisoformat(start[:10])
        if end:
            end_date = datetime.date.fromisoformat(end[:10])

    except ValueError:
        print(">>> ERROR parseando fechas:", start, end)
        return JsonResponse({"error": "Fechas inválidas"}, status=400)

    qs = Ausencia.objects.all()

    # Filtramos por rango de fechas solapadas con el rango visible
    if start_date and end_date:
        qs = qs.filter(
            fecha_inicio__lte=end_date,
            fecha_fin__gte=start_date,
        )

    user = request.user

    # Permisos / visibilidad básica
    if not user.is_staff:
        qs = qs.filter(empleado=user)
    else:
        if vista == "mis":
            qs = qs.filter(empleado=user)
        # 'departamento' / 'global' de momento devuelven todas

    eventos = []
    qs = qs.select_related("empleado")

    for a in qs:
        end_plus_one = a.fecha_fin + datetime.timedelta(days=1)
        empleado_nombre = a.empleado.get_full_name() or a.empleado.username
        color = COLOR_ESTADO.get(a.estado, "#2196f3")

        eventos.append({
            "id": a.id,
            "title": f"{empleado_nombre} ({a.get_tipo_display()})",
            "start": a.fecha_inicio.isoformat(),
            "end": end_plus_one.isoformat(),
            "allDay": True,
            "backgroundColor": color,
            "borderColor": color,
            "extendedProps": {
                "tipo": a.tipo,
                "tipo_label": a.get_tipo_display(),
                "estado": a.estado,
                "empleado": empleado_nombre,
                "motivo": a.motivo,
                "horas": float(a.horas) if a.horas is not None else None,
                "creado_en": a.creado_en.isoformat() if a.creado_en else None,
            },
        })

    print(">>> eventos devueltos:", len(eventos))
    return JsonResponse(eventos, safe=False)