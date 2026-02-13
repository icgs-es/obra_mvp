# backend/agenda/views.py
from __future__ import annotations

import csv
import datetime as _dt
import io
import json

from django.db.models import Q
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import (
    HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware, make_aware
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView

from .forms import EventoForm
from .models import Event
from .services import events_between_for_user


# ============================================================
# Helpers permisos / datetime
# ============================================================
def user_is_manager(user) -> bool:
    """Gerencia/Admin: superuser, staff, o grupo 'Gerencia'/'Administradores'."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    return user.groups.filter(name__in=["Gerencia", "Administradores"]).exists()


def can_edit_event(user, ev: Event) -> bool:
    """Manager, creador o invitado puede editar (ajustable)."""
    if user_is_manager(user):
        return True
    if ev.created_by_id == user.id:
        return True
    return ev.who_users.filter(id=user.id).exists()


def _parse_to_aware(dt_str: str | None):
    """ISO -> aware datetime. None si no parsea."""
    if not dt_str:
        return None
    dt = parse_datetime(dt_str)
    if dt is None:
        return None
    return dt if is_aware(dt) else make_aware(dt)


def _append_note_line(ev: Event, label: str, value: str | None):
    """
    Mientras no existan campos nativos para ciertos extras, los guardamos en description.
    Formato: "[Label] value"
    """
    value = (value or "").strip()
    if not value:
        return
    desc = ev.description or ""
    line = f"\n[{label}] {value}"
    if line not in desc:
        ev.description = desc + line


def _save_extra_fields_into_description(ev: Event, form: forms.Form, request):
    """
    Guarda extras tipo TeamUp (si tu form los trae) dentro de description.
    """
    _append_note_line(ev, "Calendario", form.cleaned_data.get("calendario"))
    _append_note_line(ev, "Estado tarea", form.cleaned_data.get("estado_tarea"))

    rrule = form.cleaned_data.get("rrule")
    rrule_until = form.cleaned_data.get("rrule_until")
    if rrule or rrule_until:
        txt = rrule or "-"
        if rrule_until:
            until_dt = rrule_until if is_aware(rrule_until) else make_aware(rrule_until)
            txt += f" | UNTIL={until_dt.isoformat()}"
        _append_note_line(ev, "RRULE", txt)

    _append_note_line(ev, "Quién", form.cleaned_data.get("quien_texto"))

    for f in request.FILES.getlist("adjuntos"):
        _append_note_line(ev, "Adjunto", getattr(f, "name", "archivo"))

    ev.save(update_fields=["description"])


def _layer_to_visibility_values(layers: list[str]) -> list[str]:
    """
    Map capas UI -> choices del modelo:
    mis -> PRIVADA
    depto -> DEPARTAMENTO
    global -> GLOBAL
    """
    vis = []
    if "global" in layers:
        vis.append("GLOBAL")
    if "depto" in layers:
        vis.append("DEPARTAMENTO")
    if "mis" in layers:
        vis.append("PRIVADA")
    return vis


# ============================================================
# Pantallas
# ============================================================
@login_required
def calendar_view(request):
    """Plantilla FullCalendar; eventos se cargan vía api_events."""
    return render(request, "agenda/calendar.html")


class AgendaView(LoginRequiredMixin, TemplateView):
    template_name = "agenda/agenda.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        start = make_aware(_dt.datetime.combine(hoy, _dt.time.min))
        end = start + timezone.timedelta(days=7)
        ctx["eventos"] = Event.objects.filter(start__gte=start, start__lt=end).order_by("start")
        ctx["hoy"] = hoy
        return ctx


# ============================================================
# API: capas (simulan "calendarios" por visibilidad)
# ============================================================
@login_required
def api_calendars(request):
    data = [
        {"id": "mis", "name": "Mis eventos", "scope": "PRIVATE"},
        {"id": "depto", "name": "Departamento", "scope": "TEAM"},
        {"id": "global", "name": "Global", "scope": "ORG"},
    ]
    return JsonResponse(data, safe=False)

import logging
logger = logging.getLogger(__name__)

# ============================================================
# API: eventos (FullCalendar)
# ============================================================

@require_http_methods(["GET", "POST"])
@login_required
def api_events(request):
    """
    GET: lista eventos (FullCalendar)
    POST: crea evento rápido (desde modal)
    """

    # -------------------------
    # POST (crear)
    # -------------------------
    if request.method == "POST":
        logger.error("API_EVENTS POST LLEGÓ")
        try:
            data = json.loads(request.body.decode("utf-8"))
        except Exception:
            return HttpResponseBadRequest("JSON inválido")

        title = (data.get("title") or "").strip()
        start = data.get("start")
        end = data.get("end")
        all_day = data.get("allDay")
        ubicacion = (data.get("ubicacion") or "").strip()
        vis = (data.get("visibilidad") or "privada").strip().lower()

        if not title:
            return HttpResponseBadRequest("Falta title")
        if not start:
            return HttpResponseBadRequest("Falta start")

        start_dt = _parse_to_aware(start)
        end_dt = _parse_to_aware(end) if end else None
        if not start_dt:
            return HttpResponseBadRequest("start inválido")

        all_day_bool = bool(all_day)

        if all_day_bool and end_dt is None:
            end_dt = start_dt

        if end_dt and end_dt < start_dt:
            return HttpResponseBadRequest("fin < inicio")

        if vis not in ("privada", "depto", "global"):
            vis = "privada"

        # 👉 OJO: usa el modelo correcto (en tu archivo aparece Event)
        ev = Event.objects.create(
            titulo=title,
            inicio=start_dt,
            fin=end_dt,
            all_day=all_day_bool,
            visibilidad=vis,
            ubicacion=ubicacion,
            notas="",
        )

        # opcional: si tienes asistentes M2M y quieres auto-asignar al creador
        try:
            ev.asistentes.add(request.user)
        except Exception:
            pass

        return JsonResponse({
            "id": ev.id,
            "title": ev.titulo,
            "start": ev.inicio.isoformat(),
            "end": (ev.fin or ev.inicio).isoformat(),
            "allDay": bool(ev.all_day),
            "extendedProps": {
                "ubicacion": ev.ubicacion,
                "visibilidad": ev.visibilidad,
            }
        }, status=201)

    # -------------------------
    # GET (listar) - tu código actual
    # -------------------------
    start = request.GET.get("start")
    end = request.GET.get("end")
    layers = request.GET.getlist("calendar")

    if not (start and end):
        return HttpResponseBadRequest("Missing start/end")

    start_dt = _parse_to_aware(start)
    end_dt = _parse_to_aware(end)
    if not start_dt or not end_dt:
        return HttpResponseBadRequest("Invalid start/end")

    base = Event.objects.all()

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

    filtered = events_between_for_user(request.user, start_dt, end_dt, base)

    data_out = []
    for e in filtered:
        end_val = e.fin or e.inicio
        data_out.append({
            "id": e.id,
            "title": e.titulo,
            "start": e.inicio.isoformat(),
            "end": end_val.isoformat(),
            "allDay": bool(e.all_day),
            "extendedProps": {
                "ubicacion": e.ubicacion,
                "visibilidad": e.visibilidad,
            }
        })
    return JsonResponse(data_out, safe=False)

# ============================================================
# API: detalle evento (PATCH drag/resize; DELETE)
# ============================================================
@require_http_methods(["PATCH", "DELETE"])
@login_required
def api_event_detail(request, pk: int):
    ev = get_object_or_404(Event, pk=pk)
    if not can_edit_event(request.user, ev):
        return HttpResponseForbidden("Sin permisos")

    if request.method == "DELETE":
        ev.delete()
        return JsonResponse({"ok": True})

    # PATCH JSON
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return HttpResponseBadRequest("JSON inválido")

    start = payload.get("start")
    end = payload.get("end")
    all_day = payload.get("allDay")

    if start:
        ev.start = _parse_to_aware(start) or ev.start
    if end is not None:
        ev.end = _parse_to_aware(end)
    if all_day is not None:
        ev.all_day = bool(all_day)
        if ev.all_day and ev.end is None:
            ev.end = ev.start

    if ev.end and ev.end < ev.start:
        return HttpResponseBadRequest("end < start")

    ev.save(update_fields=["start", "end", "all_day"])
    return JsonResponse({"ok": True})


# ============================================================
# CRUD (FBVs) usando el EventoForm existente
# ============================================================
@login_required
def create_view(request):
    if request.method == "POST":
        form = EventoForm(request.POST, request.FILES)
        if form.is_valid():
            ev = form.save(commit=False)
            # Normaliza all_day
            if getattr(ev, "all_day", False) and not getattr(ev, "end", None):
                ev.end = ev.start
            ev.created_by = request.user
            ev.save()
            form.save_m2m()
            _save_extra_fields_into_description(ev, form, request)

            messages.success(request, "Evento creado.")
            return redirect("agenda:home")
    else:
        initial = {}
        start_qs = request.GET.get("start")
        end_qs = request.GET.get("end")
        all_day_qs = request.GET.get("allDay")

        start_dt = _parse_to_aware(start_qs) if start_qs else None
        end_dt = _parse_to_aware(end_qs) if end_qs else None
        
        def _to_local_input(dt):
            if not dt:
                return None
            return dt.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%dT%H:%M")
        
        # OJO: nombres de campo según tu form/model (en tu caso ya estamos en Event: start/end)
        if start_dt:
            initial["start"] = _to_local_input(start_dt)

            # Si no viene fin (click simple), ponemos +1 hora por defecto
            if not end_dt:
                end_dt = start_dt + timezone.timedelta(hours=1)

        if end_dt:
            initial["end"] = _to_local_input(end_dt)

        if all_day_qs is not None:
            initial["all_day"] = all_day_qs in ("1", "true", "True", "yes")
            
        if all_day_qs in ("1", "true", "True", "yes") and start_dt:
            # Para todo el día, dejamos fin igual que inicio
            end_dt = start_dt
            initial["end"] = _to_local_input(end_dt)

        form = EventoForm(initial=initial)

    return render(request, "agenda/form.html", {"form": form, "mode": "create"})


@login_required
def update_view(request, pk: int):
    ev = get_object_or_404(Event, pk=pk)
    if not can_edit_event(request.user, ev):
        return HttpResponseForbidden("Sin permisos")

    if request.method == "POST":
        form = EventoForm(request.POST, request.FILES, instance=ev)
        if form.is_valid():
            ev = form.save(commit=False)
            if getattr(ev, "all_day", False) and not getattr(ev, "end", None):
                ev.end = ev.start
            ev.save()
            form.save_m2m()
            _save_extra_fields_into_description(ev, form, request)

            messages.success(request, "Evento actualizado.")
            return redirect("agenda:home")
    else:
        form = EventoForm(instance=ev)
    return render(request, "agenda/form.html", {"form": form, "mode": "update", "obj": ev})


# ============================================================
# Import / Export
# ============================================================
@login_required
def import_view(request):
    """
    Importa CSV compatible:
    - Esquema antiguo: titulo/inicio/fin/all_day/visibilidad/ubicacion/notas
    - TeamUp: Subject/Start Date/Start Time/End Date/End Time/All day/...
    """
    if request.method == "POST" and request.FILES.get("file"):
        f = request.FILES["file"]
        raw = f.read().decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(raw))
        created = 0

        def parse_bool(v):
            v = (v or "").strip().lower()
            return v in ("1", "true", "yes", "y", "t", "sí", "si")

        def parse_date_parts(d, t):
            if not d:
                return None
            d = d.strip()
            t = (t or "").strip()

            if t and ":" not in t:
                try:
                    vv = float(t.replace(",", "."))
                    hh = int(vv)
                    mm = int(round((vv - hh) * 60))
                    t = f"{hh:02d}:{mm:02d}"
                except Exception:
                    t = "00:00"
            if not t:
                t = "00:00"

            for fmt in ("%d/%m/%Y %H:%M", "%d-%m-%y %H:%M", "%Y-%m-%d %H:%M"):
                try:
                    dt = _dt.datetime.strptime(f"{d} {t}", fmt)
                    return make_aware(dt)
                except Exception:
                    continue
            return _parse_to_aware(f"{d}T{t}:00")

        def normalize_visibility(v: str | None) -> str:
            v = (v or "PRIVADA").strip().upper()
            # acepta antiguas
            if v in ("PRIVADA", "PRIVATE"):
                return "PRIVADA"
            if v in ("DEPTO", "DEPARTAMENTO", "TEAM"):
                return "DEPARTAMENTO"
            if v in ("GLOBAL", "ORG"):
                return "GLOBAL"
            return "PRIVADA"

        for row in reader:
            title = row.get("title") or row.get("titulo") or row.get("Subject")
            if not title:
                continue

            start_raw = row.get("start") or row.get("inicio")
            end_raw = row.get("end") or row.get("fin")

            if not start_raw:
                start_dt = parse_date_parts(row.get("Start Date"), row.get("Start Time"))
            else:
                start_dt = _parse_to_aware(start_raw)

            if not end_raw:
                ed = row.get("End Date")
                et = row.get("End Time")
                end_dt = parse_date_parts(ed, et) if (ed or et) else None
            else:
                end_dt = _parse_to_aware(end_raw)

            if not start_dt:
                continue

            all_day = parse_bool(row.get("all_day") or row.get("All day"))
            if all_day and not end_dt:
                end_dt = start_dt

            visibility = normalize_visibility(row.get("visibility") or row.get("visibilidad"))
            location = row.get("location") or row.get("ubicacion") or row.get("Location") or ""
            description = row.get("description") or row.get("notas") or row.get("Description") or ""

            ev = Event.objects.create(
                title=title,
                start=start_dt,
                end=end_dt,
                all_day=all_day,
                visibility=visibility,
                location=location,
                description=description,
                created_by=request.user,
            )

            # extras TeamUp -> description
            estado = (row.get("ESTADO TAREA") or "").strip()
            quien = (row.get("Who") or "").strip()
            rrule = (row.get("Repeats") or "").strip()
            runtil = (row.get("Repeats Until") or "").strip()

            if estado:
                _append_note_line(ev, "Estado tarea", estado)
            if quien:
                _append_note_line(ev, "Quién", quien)
            if rrule or runtil:
                txt = rrule or "-"
                if runtil:
                    txt += f" | UNTIL={runtil}"
                _append_note_line(ev, "RRULE", txt)

            ev.save()
            created += 1

        messages.success(request, f"Importados {created} eventos.")
        return redirect("agenda:home")

    return render(request, "agenda/import.html")


@login_required
def export_view(request):
    """
    Exporta CSV por rango (?start=YYYY-MM-DD&end=YYYY-MM-DD) y por capas (&calendar=mis|depto|global).
    """
    start = request.GET.get("start") or (_dt.date.today().isoformat())
    end = request.GET.get("end") or (_dt.date.today() + _dt.timedelta(days=30)).isoformat()
    layers = request.GET.getlist("calendar")

    start_dt = _parse_to_aware(start + "T00:00:00")
    end_dt = _parse_to_aware(end + "T23:59:59")
    if not start_dt or not end_dt:
        return HttpResponseBadRequest("Invalid start/end")

    base = Event.objects.filter(start__lt=end_dt).filter(
        Q(end__gte=start_dt) | Q(end__isnull=True)
    )

    if layers:
        vis_list = _layer_to_visibility_values(layers)
        if vis_list:
            base = base.filter(visibility__in=vis_list)

    qs = events_between_for_user(request.user, start_dt, end_dt, base)

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["title", "start", "end", "all_day", "visibility", "location", "description"])
    for e in qs:
        w.writerow([
            e.title,
            e.start.isoformat(),
            (e.end or e.start).isoformat(),
            "1" if e.all_day else "0",
            e.visibility,
            e.location or "",
            (e.description or "").replace("\n", " ").strip(),
        ])

    resp = HttpResponse(out.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="agenda_export.csv"'
    return resp


# ============================================================
# ICS feed (token simple en memoria)
# ============================================================
TOKENS: dict[str, int] = {}  # {token: user_id}


@login_required
def ics_feed(request, token: str):
    user_id = TOKENS.get(token)
    if not user_id or user_id != request.user.id:
        return HttpResponseForbidden("Token inválido")

    start_dt = make_aware(_dt.datetime.now()) - _dt.timedelta(days=30)
    end_dt = start_dt + _dt.timedelta(days=90)
    qs = events_between_for_user(request.user, start_dt, end_dt, Event.objects.all())

    def esc(s: str) -> str:
        s = (s or "")
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//INTASA//Agenda//ES"]
    for e in qs:
        uid = f"intasa-{e.id}@agenda"
        dtstart = (e.start.astimezone(_dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        dtend = ((e.end or e.start).astimezone(_dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"SUMMARY:{esc(e.title)}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"LOCATION:{esc(e.location)}",
            f"DESCRIPTION:{esc(e.description)}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    txt = "\r\n".join(lines) + "\r\n"
    return HttpResponse(txt, content_type="text/calendar; charset=utf-8")
