from __future__ import annotations

import csv
import datetime as dt
import io
import json
import logging
import uuid

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.timezone import (
    is_aware,
    make_aware,
)
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView

from .access import (
    editable_events_for_user,
    resolve_active_agenda_team,
    resolve_calendar_for_event,
    user_can_edit_event,
    user_is_agenda_manager,
    visible_events_for_user,
)
from .activity import (
    registrar_cambio_evento,
    registrar_creacion_evento,
    registrar_eliminacion_evento,
    registrar_importacion_eventos,
    snapshot_evento,
)
from .forms import EventoForm
from .models import Event
from .integration import unified_calendar_items
from .services import events_between_for_user


logger = logging.getLogger(__name__)
User = get_user_model()


def _active_team_id(request):
    return request.session.get(
        "active_team_id",
        "all",
    )


def _get_active_team(request):
    """Alias histórico con resolución estricta."""
    return resolve_active_agenda_team(
        request
    )


def user_is_manager(user):
    return user_is_agenda_manager(
        user
    )


def can_edit_event(
    user,
    event,
    active_team_id="all",
):
    return user_can_edit_event(
        user,
        event,
        active_team_id=active_team_id,
    )


def _get_user_color(user):
    if not user or not getattr(
        user,
        "pk",
        None,
    ):
        return None

    try:
        from usuarios.models import UserProfile

        profile = UserProfile.objects.get(
            user_id=user.pk
        )

        return profile.color or None

    except Exception:
        mapping = getattr(
            settings,
            "AGENDA_USER_COLORS",
            {},
        ) or {}

        return mapping.get(user.pk)


def _parse_to_aware(value):
    if not value:
        return None

    parsed = parse_datetime(
        str(value)
    )

    if parsed is None:
        return None

    if is_aware(parsed):
        return parsed

    return make_aware(parsed)


def _parse_bool(value):
    if isinstance(value, bool):
        return value

    return str(
        value or ""
    ).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "t",
        "si",
        "sí",
    }


def _minute_key(value):
    if value is None:
        return None

    if not is_aware(value):
        value = make_aware(value)

    return (
        value
        .astimezone(dt.timezone.utc)
        .replace(
            second=0,
            microsecond=0,
        )
    )


def _preserve_subminute_precision(
    evento,
    evento_persistido,
):
    """Conserva segundos y microsegundos no editables en el formulario.

    datetime-local envía precisión de minutos. Si el usuario mantiene
    el mismo minuto visible, no debe modificarse el valor persistido ni
    generarse una reprogramación funcional falsa.
    """
    preserved_fields = []

    for field_name in (
        "start",
        "end",
        "rrule_until",
    ):
        previous_value = getattr(
            evento_persistido,
            field_name,
            None,
        )

        submitted_value = getattr(
            evento,
            field_name,
            None,
        )

        if (
            previous_value is not None
            and submitted_value is not None
            and _minute_key(
                previous_value
            )
            == _minute_key(
                submitted_value
            )
        ):
            setattr(
                evento,
                field_name,
                previous_value,
            )

            preserved_fields.append(
                field_name
            )

    return preserved_fields


def _preserve_unchanged_legacy_status(evento, evento_persistido, request):
    """No convierte un estado legacy en un cambio funcional al regrabarlo.

    El formulario normaliza los estados legacy abiertos para poder mostrarlos
    con las opciones actuales. Si el usuario no modificó ese valor, conservar
    el persistido evita una actividad de cambio falsa.
    """
    submitted = str(request.POST.get("status") or "").strip()
    legacy_open = {
        Event.LegacyTaskStatus.PENDIENTE,
        Event.LegacyTaskStatus.EN_PROCESO,
        Event.LegacyTaskStatus.BLOQUEADA,
    }
    if (
        submitted == evento_persistido.status
        and evento_persistido.status in legacy_open
        and evento.status == Event.Status.PROGRAMADO
    ):
        evento.status = evento_persistido.status



def _append_note_line(
    event,
    label,
    value,
):
    value = str(
        value or ""
    ).strip()

    if not value:
        return

    line = f"\n[{label}] {value}"

    if line not in (
        event.description or ""
    ):
        event.description = (
            event.description or ""
        ) + line


def _save_extra_fields_into_description(
    event,
    form,
    request,
):
    previous = event.description or ""

    rrule = form.cleaned_data.get(
        "rrule"
    )

    rrule_until = form.cleaned_data.get(
        "rrule_until"
    )

    if rrule or rrule_until:
        text = rrule or "-"

        if rrule_until:
            until_value = (
                rrule_until
                if is_aware(rrule_until)
                else make_aware(
                    rrule_until
                )
            )

            text += (
                " | UNTIL="
                + until_value.isoformat()
            )

        _append_note_line(
            event,
            "RRULE",
            text,
        )

    _append_note_line(
        event,
        "Quién",
        form.cleaned_data.get(
            "who_text"
        ),
    )

    for uploaded_file in (
        request.FILES.getlist(
            "adjuntos"
        )
    ):
        _append_note_line(
            event,
            "Adjunto",
            getattr(
                uploaded_file,
                "name",
                "archivo",
            ),
        )

    if event.description != previous:
        event.save(
            update_fields=[
                "description",
                "updated_at",
            ]
        )


def _layer_to_visibility_values(
    layers,
):
    values = []

    if "global" in layers:
        values.append(
            Event.Visibility.GLOBAL
        )

    if "depto" in layers:
        values.append(
            Event.Visibility.DEPARTAMENTO
        )

    if "mis" in layers:
        values.append(
            Event.Visibility.PRIVADA
        )

    return values


def _resolve_calendar_for_quick_event(
    request,
    visibility,
    payload,
):
    explicit_id = (
        payload.get("calendar")
        or payload.get("calendar_id")
    )

    return resolve_calendar_for_event(
        user=request.user,
        visibility=visibility,
        explicit_id=explicit_id,
    )


@login_required
def calendar_view(request):
    return render(
        request,
        "agenda/calendar.html",
        {
            "active_agenda_team": (
                resolve_active_agenda_team(
                    request
                )
            ),
        },
    )


class AgendaView(
    LoginRequiredMixin,
    TemplateView,
):
    template_name = "agenda/agenda.html"

    def get_context_data(
        self,
        **kwargs,
    ):
        context = super().get_context_data(
            **kwargs
        )

        today = timezone.localdate()

        start = make_aware(
            dt.datetime.combine(
                today,
                dt.time.min,
            )
        )

        end = (
            start
            + dt.timedelta(days=7)
        )

        context["eventos"] = (
            visible_events_for_user(
                self.request.user,
                active_team_id=(
                    _active_team_id(
                        self.request
                    )
                ),
            )
            .filter(
                start__gte=start,
                start__lt=end,
            )
            .order_by("start")
        )

        context["hoy"] = today

        return context


@login_required
def api_calendars(request):
    return JsonResponse(
        [
            {
                "id": "mis",
                "name": "Mis eventos",
                "scope": "PRIVATE",
            },
            {
                "id": "depto",
                "name": "Departamento",
                "scope": "TEAM",
            },
            {
                "id": "global",
                "name": "Global",
                "scope": "ORG",
            },
        ],
        safe=False,
    )


@require_http_methods([
    "GET",
    "POST",
])
@login_required
def api_events(request):
    # AGENDA_USER_COLORS_V1_3 · presentación visual únicamente
    from .user_colors import (
        build_user_color_map,
        event_color_payload,
        event_identity_payload,
    )

    agenda_user_map = build_user_color_map()
    if request.method == "POST":
        try:
            payload = json.loads(
                request.body.decode(
                    "utf-8"
                )
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            logger.warning(
                (
                    "Agenda API: JSON inválido "
                    "user_id=%s"
                ),
                request.user.pk,
            )

            return HttpResponseBadRequest(
                "JSON inválido."
            )

        if not isinstance(
            payload,
            dict,
        ):
            return HttpResponseBadRequest(
                "JSON inválido."
            )

        title = str(
            payload.get("title")
            or ""
        ).strip()

        start_value = (
            payload.get("start")
            or payload.get("startStr")
        )

        end_value = (
            payload.get("end")
            or payload.get("endStr")
        )

        if not title:
            return HttpResponseBadRequest(
                "Falta el título."
            )

        if not start_value:
            return HttpResponseBadRequest(
                "Falta la fecha de inicio."
            )

        start = _parse_to_aware(
            start_value
        )

        end = (
            _parse_to_aware(
                end_value
            )
            if end_value
            else None
        )

        if start is None:
            return HttpResponseBadRequest(
                "Fecha de inicio inválida."
            )

        all_day = _parse_bool(
            payload.get("allDay")
        )

        if all_day and end is None:
            end = start

        if end and end < start:
            return HttpResponseBadRequest(
                (
                    "La fecha de fin no puede "
                    "ser anterior al inicio."
                )
            )

        visibility_value = str(
            payload.get("visibility")
            or payload.get("visibilidad")
            or "privada"
        ).strip().lower()

        visibility = {
            "privada": (
                Event.Visibility.PRIVADA
            ),
            "depto": (
                Event.Visibility.DEPARTAMENTO
            ),
            "departamento": (
                Event.Visibility.DEPARTAMENTO
            ),
            "global": (
                Event.Visibility.GLOBAL
            ),
        }.get(
            visibility_value,
            Event.Visibility.PRIVADA,
        )

        team = (
            resolve_active_agenda_team(
                request
            )
        )

        if team is None:
            return HttpResponseBadRequest(
                (
                    "Selecciona una empresa "
                    "concreta antes de crear "
                    "el evento."
                )
            )

        calendar = (
            _resolve_calendar_for_quick_event(
                request,
                visibility,
                payload,
            )
        )

        if calendar is None:
            return HttpResponseBadRequest(
                (
                    "No existe un calendario "
                    "activo compatible con la "
                    "visibilidad seleccionada."
                )
            )

        with transaction.atomic():
            event = Event.objects.create(
                title=title,
                calendar=calendar,
                start=start,
                end=end,
                all_day=all_day,
                visibility=visibility,
                location=str(
                    payload.get("location")
                    or payload.get(
                        "ubicacion"
                    )
                    or ""
                ).strip(),
                description="",
                created_by=request.user,
                team=team,
            )

            registrar_creacion_evento(
                evento=event,
                actor=request.user,
                fuente="api",
            )

        return JsonResponse(
            {
                "id": event.pk,
                "title": event.title,
                "start": (
                    event.start.isoformat()
                ),
                "end": (
                    event.end
                    or event.start
                ).isoformat(),
                "allDay": bool(
                    event.all_day
                ),
                **event_color_payload(event, agenda_user_map),
                "extendedProps": {
                    **event_identity_payload(event, agenda_user_map),
                    "location": (
                        event.location
                    ),
                    "visibility": (
                        event.visibility
                    ),
                    "edit_url": reverse(
                        "agenda:edit",
                        args=[event.pk],
                    ),
                },
            },
            status=201,
        )

    start = _parse_to_aware(
        request.GET.get("start")
    )

    end = _parse_to_aware(
        request.GET.get("end")
    )

    if start is None or end is None:
        return HttpResponseBadRequest(
            "Faltan start/end válidos."
        )

    base_queryset = Event.objects.all()

    layers = request.GET.getlist(
        "calendar"
    )

    if layers:
        visibility_values = (
            _layer_to_visibility_values(
                layers
            )
        )

        if visibility_values:
            base_queryset = (
                base_queryset.filter(
                    visibility__in=(
                        visibility_values
                    )
                )
            )

    active_team_id = (
        _active_team_id(request)
    )

    result = unified_calendar_items(
        request.user,
        start,
        end,
        agenda_user_map,
        active_team_id=active_team_id,
        event_queryset=base_queryset,
        visibility_values=(visibility_values if layers else None),
    )

    return JsonResponse(
        result,
        safe=False,
    )


@require_http_methods(["POST"])
@login_required
def event_action(request, pk):
    event = get_object_or_404(
        editable_events_for_user(
            request.user,
            active_team_id=_active_team_id(request),
        ),
        pk=pk,
    )
    action = str(request.POST.get("action") or "").strip().lower()
    status_by_action = {
        "complete": Event.Status.COMPLETADO,
        "reopen": Event.Status.PROGRAMADO,
        "cancel": Event.Status.CANCELADO,
    }
    if action not in status_by_action:
        return HttpResponseBadRequest("Acción no válida.")
    anterior = snapshot_evento(event)
    event.status = status_by_action[action]
    event.updated_by = request.user
    with transaction.atomic():
        event.save(update_fields=["status", "updated_by", "updated_at"])
        registrar_cambio_evento(
            evento=event,
            actor=request.user,
            anterior=anterior,
            fuente="agenda_action",
        )
    return JsonResponse({"ok": True, "status": event.status})


@require_http_methods([
    "PATCH",
    "DELETE",
])
@login_required
def api_event_detail(
    request,
    pk,
):
    active_team_id = (
        _active_team_id(request)
    )

    event = get_object_or_404(
        editable_events_for_user(
            request.user,
            active_team_id=active_team_id,
        ),
        pk=pk,
    )

    if request.method == "DELETE":
        anterior = snapshot_evento(
            event
        )

        with transaction.atomic():
            registrar_eliminacion_evento(
                evento=event,
                actor=request.user,
                anterior=anterior,
                fuente="api",
            )

            event.delete()

        return JsonResponse({
            "ok": True,
        })

    try:
        payload = json.loads(
            request.body.decode(
                "utf-8"
            )
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):
        return HttpResponseBadRequest(
            "JSON inválido."
        )

    if not isinstance(
        payload,
        dict,
    ):
        return HttpResponseBadRequest(
            "JSON inválido."
        )

    anterior = snapshot_evento(
        event
    )

    if payload.get("start"):
        parsed_start = _parse_to_aware(
            payload["start"]
        )

        if parsed_start is None:
            return HttpResponseBadRequest(
                "Fecha de inicio inválida."
            )

        event.start = parsed_start

    if "end" in payload:
        if payload.get("end"):
            parsed_end = (
                _parse_to_aware(
                    payload["end"]
                )
            )

            if parsed_end is None:
                return HttpResponseBadRequest(
                    "Fecha de fin inválida."
                )

            event.end = parsed_end

        else:
            event.end = None

    if "allDay" in payload:
        event.all_day = _parse_bool(
            payload.get("allDay")
        )

        if (
            event.all_day
            and event.end is None
        ):
            event.end = event.start

    if (
        event.end
        and event.end < event.start
    ):
        return HttpResponseBadRequest(
            (
                "La fecha de fin no puede "
                "ser anterior al inicio."
            )
        )

    event.updated_by = request.user

    with transaction.atomic():
        event.save(
            update_fields=[
                "start",
                "end",
                "all_day",
                "updated_by",
                "updated_at",
            ]
        )

        registrar_cambio_evento(
            evento=event,
            actor=request.user,
            anterior=anterior,
            fuente="api",
        )

    return JsonResponse({
        "ok": True,
    })


@login_required
def create_view(request):
    team = resolve_active_agenda_team(
        request
    )

    available_agenda_teams = (
        request.user.teams
        .order_by(
            "name",
            "pk",
        )
    )

    selected_agenda_team_id = ""

    if (
        team is None
        and request.method == "POST"
    ):
        selected_agenda_team_id = (
            request.POST.get("team")
            or ""
        ).strip()

        if (
            selected_agenda_team_id
            .isdigit()
        ):
            team = (
                available_agenda_teams
                .filter(
                    pk=int(
                        selected_agenda_team_id
                    )
                )
                .first()
            )

    if request.method == "POST":
        form = EventoForm(
            request.POST,
            request.FILES,
            user=request.user,
            team=team,
        )

        is_valid = form.is_valid()

        if team is None:
            form.add_error(
                None,
                (
                    "Selecciona una empresa "
                    "concreta antes de crear "
                    "el evento."
                ),
            )

        elif is_valid:
            with transaction.atomic():
                event = form.save(
                    commit=False
                )

                if (
                    event.all_day
                    and not event.end
                ):
                    event.end = event.start

                event.created_by = (
                    request.user
                )

                event.team = team
                event.save()

                form.save_m2m()

                _save_extra_fields_into_description(
                    event,
                    form,
                    request,
                )

                registrar_creacion_evento(
                    evento=event,
                    actor=request.user,
                    fuente="formulario",
                )

            messages.success(
                request,
                "Evento creado.",
            )

            return redirect(
                "agenda:home"
            )

    else:
        initial = {}

        start = _parse_to_aware(
            request.GET.get("start")
        )

        end = _parse_to_aware(
            request.GET.get("end")
        )

        all_day_value = (
            request.GET.get("allDay")
        )

        def to_local_input(value):
            if not value:
                return None

            return (
                value.astimezone(
                    timezone
                    .get_current_timezone()
                )
                .strftime(
                    "%Y-%m-%dT%H:%M"
                )
            )

        if start:
            initial["start"] = (
                to_local_input(start)
            )

            if not end:
                end = (
                    start
                    + dt.timedelta(hours=1)
                )

        if end:
            initial["end"] = (
                to_local_input(end)
            )

        if all_day_value is not None:
            initial["all_day"] = (
                _parse_bool(
                    all_day_value
                )
            )

        if (
            _parse_bool(all_day_value)
            and start
        ):
            initial["end"] = (
                to_local_input(start)
            )

        form = EventoForm(
            initial=initial,
            user=request.user,
            team=team,
        )

    return render(
        request,
        "agenda/form.html",
        {
            "form": form,
            "mode": "create",
            "active_agenda_team": team,
            "available_agenda_teams": (
                available_agenda_teams
            ),
            "selected_agenda_team_id": (
                selected_agenda_team_id
            ),
        },
    )


@login_required
def update_view(
    request,
    pk,
):
    event = get_object_or_404(
        editable_events_for_user(
            request.user,
            active_team_id=(
                _active_team_id(request)
            ),
        ),
        pk=pk,
    )

    if request.method == "POST":
        evento_persistido = (
            Event.objects
            .prefetch_related(
                "who_users"
            )
            .get(pk=event.pk)
        )

        anterior = snapshot_evento(
            evento_persistido
        )

        form = EventoForm(
            request.POST,
            request.FILES,
            instance=event,
            user=request.user,
            team=event.team,
        )

        if form.is_valid():
            with transaction.atomic():
                event = form.save(
                    commit=False
                )

                _preserve_subminute_precision(
                    event,
                    evento_persistido,
                )

                _preserve_unchanged_legacy_status(
                    event,
                    evento_persistido,
                    request,
                )

                if (
                    event.all_day
                    and not event.end
                ):
                    event.end = event.start

                event.updated_by = (
                    request.user
                )

                event.save()
                form.save_m2m()

                _save_extra_fields_into_description(
                    event,
                    form,
                    request,
                )

                registrar_cambio_evento(
                    evento=event,
                    actor=request.user,
                    anterior=anterior,
                    fuente="formulario",
                )

            messages.success(
                request,
                "Evento actualizado.",
            )

            return redirect(
                "agenda:home"
            )

    else:
        form = EventoForm(
            instance=event,
            user=request.user,
            team=event.team,
        )

    return render(
        request,
        "agenda/form.html",
        {
            "form": form,
            "mode": "update",
            "obj": event,
            "active_agenda_team": (
                event.team
            ),
        },
    )


@login_required
def import_view(request):
    team = resolve_active_agenda_team(
        request
    )

    if (
        request.method == "POST"
        and request.FILES.get("file")
    ):
        if team is None:
            messages.error(
                request,
                (
                    "Selecciona una empresa "
                    "concreta antes de importar "
                    "eventos."
                ),
            )

            return render(
                request,
                "agenda/import.html",
                {
                    "active_agenda_team": None,
                },
                status=400,
            )

        raw = (
            request.FILES["file"]
            .read()
            .decode(
                "utf-8",
                errors="ignore",
            )
        )

        reader = csv.DictReader(
            io.StringIO(raw)
        )

        created = 0
        skipped = 0
        created_ids = []
        created_titles = []
        operation_id = uuid.uuid4().hex

        def normalize_visibility(value):
            value = str(
                value or "PRIVADA"
            ).strip().upper()

            if value in {
                "DEPTO",
                "DEPARTAMENTO",
                "TEAM",
            }:
                return (
                    Event.Visibility
                    .DEPARTAMENTO
                )

            if value in {
                "GLOBAL",
                "ORG",
            }:
                return (
                    Event.Visibility.GLOBAL
                )

            return (
                Event.Visibility.PRIVADA
            )

        with transaction.atomic():
            for row in reader:
                title = str(
                    row.get("title")
                    or row.get("titulo")
                    or row.get("Subject")
                    or ""
                ).strip()

                start = _parse_to_aware(
                    row.get("start")
                    or row.get("inicio")
                )

                end = _parse_to_aware(
                    row.get("end")
                    or row.get("fin")
                )

                if not title or start is None:
                    skipped += 1
                    continue

                all_day = _parse_bool(
                    row.get("all_day")
                    or row.get("All day")
                )

                if all_day and end is None:
                    end = start

                if end and end < start:
                    skipped += 1
                    continue

                visibility = (
                    normalize_visibility(
                        row.get("visibility")
                        or row.get(
                            "visibilidad"
                        )
                    )
                )

                calendar = (
                    resolve_calendar_for_event(
                        user=request.user,
                        visibility=visibility,
                        explicit_id=(
                            row.get(
                                "calendar_id"
                            )
                            or None
                        ),
                    )
                )

                if calendar is None:
                    skipped += 1
                    continue

                event = Event.objects.create(
                    title=title,
                    calendar=calendar,
                    start=start,
                    end=end,
                    all_day=all_day,
                    visibility=visibility,
                    location=str(
                        row.get("location")
                        or row.get(
                            "ubicacion"
                        )
                        or ""
                    ).strip(),
                    description=str(
                        row.get("description")
                        or row.get("notas")
                        or ""
                    ),
                    created_by=request.user,
                    team=team,
                )

                created_ids.append(
                    event.pk
                )

                created_titles.append(
                    event.title
                )

                created += 1

            registrar_importacion_eventos(
                team=team,
                actor=request.user,
                evento_ids=created_ids,
                titulos=created_titles,
                omitidos=skipped,
                operation_id=operation_id,
            )

        messages.success(
            request,
            (
                f"Importados {created} "
                f"eventos. Omitidos "
                f"{skipped}."
            ),
        )

        return redirect(
            "agenda:home"
        )

    return render(
        request,
        "agenda/import.html",
        {
            "active_agenda_team": team,
        },
    )


@login_required
def export_view(request):
    try:
        start_date = dt.date.fromisoformat(
            request.GET.get("start")
            or dt.date.today().isoformat()
        )

        end_date = dt.date.fromisoformat(
            request.GET.get("end")
            or (
                dt.date.today()
                + dt.timedelta(days=30)
            ).isoformat()
        )

    except ValueError:
        return HttpResponseBadRequest(
            "Rango de fechas inválido."
        )

    start = make_aware(
        dt.datetime.combine(
            start_date,
            dt.time.min,
        )
    )

    end = make_aware(
        dt.datetime.combine(
            end_date,
            dt.time.max,
        )
    )

    base_queryset = (
        Event.objects
        .filter(start__lt=end)
        .filter(
            Q(end__gte=start)
            | Q(end__isnull=True)
        )
    )

    layers = request.GET.getlist(
        "calendar"
    )

    if layers:
        visibility_values = (
            _layer_to_visibility_values(
                layers
            )
        )

        if visibility_values:
            base_queryset = (
                base_queryset.filter(
                    visibility__in=(
                        visibility_values
                    )
                )
            )

    queryset = events_between_for_user(
        request.user,
        start,
        end,
        base_queryset,
        active_team_id=(
            _active_team_id(request)
        ),
    )

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "title",
        "start",
        "end",
        "all_day",
        "visibility",
        "location",
        "description",
    ])

    for event in queryset:
        writer.writerow([
            event.title,
            event.start.isoformat(),
            (
                event.end
                or event.start
            ).isoformat(),
            int(bool(event.all_day)),
            event.visibility,
            event.location or "",
            (
                event.description
                or ""
            )
            .replace("\n", " ")
            .strip(),
        ])

    response = HttpResponse(
        output.getvalue(),
        content_type=(
            "text/csv; charset=utf-8"
        ),
    )

    response[
        "Content-Disposition"
    ] = (
        'attachment; '
        'filename="agenda_export.csv"'
    )

    return response


TOKENS = {}


def ics_feed(
    request,
    token,
):
    user_id = TOKENS.get(token)

    if not user_id:
        return HttpResponseForbidden(
            "Token inválido"
        )

    user = User.objects.filter(
        pk=user_id,
        is_active=True,
    ).first()

    if user is None:
        return HttpResponseForbidden(
            "Token inválido"
        )

    if (
        request.user.is_authenticated
        and request.user.pk != user.pk
    ):
        return HttpResponseForbidden(
            "Token inválido"
        )

    active_team_id = "all"

    if (
        request.user.is_authenticated
        and request.user.pk == user.pk
    ):
        active_team_id = (
            _active_team_id(request)
        )

    start = (
        timezone.now()
        - dt.timedelta(days=30)
    )

    end = (
        timezone.now()
        + dt.timedelta(days=60)
    )

    queryset = events_between_for_user(
        user,
        start,
        end,
        Event.objects.all(),
        active_team_id=active_team_id,
    )

    def escape(value):
        return (
            str(value or "")
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\n", "\\n")
        )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//INTASA//Agenda//ES",
    ]

    for event in queryset:
        start_value = (
            event.start
            .astimezone(dt.timezone.utc)
            .strftime(
                "%Y%m%dT%H%M%SZ"
            )
        )

        end_value = (
            (
                event.end
                or event.start
            )
            .astimezone(dt.timezone.utc)
            .strftime(
                "%Y%m%dT%H%M%SZ"
            )
        )

        lines.extend([
            "BEGIN:VEVENT",
            (
                f"UID:intasa-{event.pk}"
                "@agenda"
            ),
            (
                "SUMMARY:"
                + escape(event.title)
            ),
            (
                "DTSTART:"
                + start_value
            ),
            (
                "DTEND:"
                + end_value
            ),
            (
                "LOCATION:"
                + escape(event.location)
            ),
            (
                "DESCRIPTION:"
                + escape(
                    event.description
                )
            ),
            "END:VEVENT",
        ])

    lines.append(
        "END:VCALENDAR"
    )

    return HttpResponse(
        "\r\n".join(lines) + "\r\n",
        content_type=(
            "text/calendar; charset=utf-8"
        ),
    )
