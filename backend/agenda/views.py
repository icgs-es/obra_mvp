from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, CreateView, UpdateView
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware, make_aware
from django.http import JsonResponse, HttpResponseBadRequest
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django import forms

from .services import events_between_for_user
from .models import Evento


# ---------- Utilidades ----------
def _parse_to_aware(dt_str):
    """
    Convierte una cadena ISO en datetime aware. Soporta cadenas con 'Z' (UTC).
    Devuelve None si no puede parsear.
    """
    dt = parse_datetime(dt_str)
    if dt is None:
        return None
    return dt if is_aware(dt) else make_aware(dt)


# ---------- Pantalla principal: calendario ----------
@login_required
def calendar_view(request):
    """
    Renderiza la plantilla con FullCalendar. Los datos van por API (api_events).
    """
    return render(request, "agenda/calendar.html")


# ---------- API: capas (simulamos "calendarios" por visibilidad) ----------
@login_required
def api_calendars(request):
    """
    Devuelve las capas disponibles para filtrar en el UI.
    """
    data = [
        {"id": "mis", "name": "Mis eventos", "scope": "PRIVATE"},
        {"id": "depto", "name": "Departamento", "scope": "TEAM"},
        {"id": "global", "name": "Global", "scope": "ORG"},
    ]
    return JsonResponse(data, safe=False)


# ---------- API: eventos ----------
@login_required
def api_events(request):
    """
    End-point compatible con FullCalendar.
    Requiere ?start=...&end=... (ISO) y opcionalmente múltiples &calendar=mis|depto|global.
    Aplica reglas de visibilidad en services.events_between_for_user.
    """
    start = request.GET.get("start")
    end = request.GET.get("end")
    layers = request.GET.getlist("calendar")  # ['mis','depto','global']

    if not (start and end):
        return HttpResponseBadRequest("Missing start/end")

    start_dt = _parse_to_aware(start)
    end_dt = _parse_to_aware(end)
    if not start_dt or not end_dt:
        return HttpResponseBadRequest("Invalid start/end")

    base = Evento.objects.all()

    # Filtro grueso por visibilidad para no traerlo todo
    if layers:
        vis_list = []
        if "global" in layers:
            vis_list.append("global")
        if "depto" in layers:
            vis_list.append("depto")
        if "mis" in layers:
            vis_list.append("privada")
        if vis_list:
            base = base.filter(visibilidad__in=vis_list)

    # Reglas finas + ventana temporal
    filtered = events_between_for_user(request.user, start_dt, end_dt, base)

    data = []
    for e in filtered:
        start_iso = e.inicio.isoformat()
        end_val = e.fin or e.inicio
        data.append({
            "id": e.id,
            "title": e.titulo,
            "start": start_iso,
            "end": end_val.isoformat(),
            "allDay": bool(e.all_day),
            "extendedProps": {
                "ubicacion": e.ubicacion,
                "visibilidad": e.visibilidad,
            }
        })
    return JsonResponse(data, safe=False)


# ---------- CRUD con CBVs ----------
class EventoForm(forms.ModelForm):
    class Meta:
        model = Evento
        fields = "__all__"


class EventoCreateView(LoginRequiredMixin, CreateView):
    template_name = "agenda/form.html"
    model = Evento
    form_class = EventoForm
    success_url = reverse_lazy("agenda:list")


class EventoUpdateView(LoginRequiredMixin, UpdateView):
    template_name = "agenda/form.html"
    model = Evento
    form_class = EventoForm
    success_url = reverse_lazy("agenda:list")


# ---------- Vista opcional (si ya la usas en otro lado) ----------
class AgendaView(LoginRequiredMixin, TemplateView):
    template_name = "agenda/agenda.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        start = timezone.make_aware(
            timezone.datetime.combine(hoy, timezone.datetime.min.time())
        )
        end = start + timezone.timedelta(days=7)
        ctx["eventos"] = Evento.objects.filter(
            inicio__gte=start, inicio__lt=end
        ).order_by("inicio")
        ctx["hoy"] = hoy
        return ctx
