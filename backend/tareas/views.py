from django.contrib.auth.mixins import (
    LoginRequiredMixin,
)
from django.db import models, transaction
import json

from django.http import HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import (
    CreateView,
    ListView,
    TemplateView,
    UpdateView,
)
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime

from .activity import (
    registrar_cambio_tarea,
    registrar_creacion_tarea,
    snapshot_tarea,
)
from .access import (
    editable_tasks_for_user,
    resolve_active_task_team,
    visible_tasks_for_user,
)
from .forms import TareaForm
from .models import Tarea


def _active_team_id(request):
    return request.session.get(
        "active_team_id",
        "all",
    )


class TareaListView(
    LoginRequiredMixin,
    ListView,
):
    template_name = "tareas/list.html"
    model = Tarea
    context_object_name = "tareas"
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            Tarea.objects
            .select_related(
                "team",
                "creador",
            )
            .prefetch_related(
                "asignados",
            )
        )

        queryset = visible_tasks_for_user(
            self.request.user,
            active_team_id=_active_team_id(
                self.request
            ),
            queryset=queryset,
        ).order_by("-creado")

        filter_value = self.request.GET.get(
            "f"
        )

        today = timezone.localdate()

        if filter_value == "hoy":
            queryset = queryset.filter(
                vencimiento=today
            )

        elif filter_value == "atrasadas":
            queryset = queryset.exclude(estado="hecha").exclude(
                seguimiento_atrasos_desde__isnull=True
            ).filter(
                models.Q(fin_programado__lt=timezone.now())
                | models.Q(
                    fin_programado__isnull=True,
                    inicio_programado__lt=timezone.now(),
                )
                | models.Q(
                    fin_programado__isnull=True,
                    inicio_programado__isnull=True,
                    vencimiento__lt=today,
                )
            )

        return queryset


class TareaCreateView(
    LoginRequiredMixin,
    CreateView,
):
    template_name = "tareas/form.html"
    model = Tarea
    form_class = TareaForm
    success_url = reverse_lazy(
        "tareas:list"
    )

    def get_task_team(self):
        return resolve_active_task_team(
            self.request
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        kwargs.update({
            "user": self.request.user,
            "team": self.get_task_team(),
        })

        return kwargs

    def get_context_data(
        self,
        **kwargs,
    ):
        context = super().get_context_data(
            **kwargs
        )

        context["mode"] = "create"
        context["active_task_team"] = (
            self.get_task_team()
        )

        return context

    def form_valid(self, form):
        # La empresa validada en el formulario es la fuente de verdad de la
        # tarea. El selector global solo propone una empresa inicial y filtra
        # pantallas; no puede invalidar un POST autorizado.
        team = form.cleaned_data["team"]

        with transaction.atomic():
            self.object = form.save(
                commit=False
            )

            self.object.creador = (
                self.request.user
            )

            self.object.team = team
            self.object.save()

            form.save_m2m()

            self.object.asignados.add(
                self.request.user
            )

            registrar_creacion_tarea(
                tarea=self.object,
                actor=self.request.user,
            )

        return HttpResponseRedirect(
            self.get_success_url()
        )

    def get_success_url(self):
        if self.request.POST.get(
            "save_add_another"
        ):
            return reverse(
                "tareas:create"
            )

        return super().get_success_url()


class TareaUpdateView(
    LoginRequiredMixin,
    UpdateView,
):
    template_name = "tareas/form.html"
    model = Tarea
    form_class = TareaForm
    success_url = reverse_lazy(
        "tareas:list"
    )

    def get_queryset(self):
        queryset = (
            Tarea.objects
            .select_related(
                "team",
                "creador",
            )
            .prefetch_related(
                "asignados",
            )
        )

        return editable_tasks_for_user(
            self.request.user,
            active_team_id=_active_team_id(
                self.request
            ),
            queryset=queryset,
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        kwargs.update({
            "user": self.request.user,
            "team": self.object.team,
        })

        return kwargs

    def get_context_data(
        self,
        **kwargs,
    ):
        context = super().get_context_data(
            **kwargs
        )

        context["mode"] = "edit"
        context["active_task_team"] = (
            self.object.team
        )

        return context

    def form_valid(self, form):
        # ModelForm ya ha aplicado cleaned_data sobre
        # self.object durante is_valid(). Para obtener
        # el estado funcional realmente anterior hay
        # que leer una instancia nueva de la base de datos.
        tarea_persistida = (
            Tarea.objects
            .select_related(
                "team",
                "creador",
            )
            .prefetch_related(
                "asignados",
            )
            .get(pk=self.object.pk)
        )

        anterior = snapshot_tarea(
            tarea_persistida
        )

        with transaction.atomic():
            self.object = form.save(
                commit=False
            )

            self.object.save()
            form.save_m2m()

            if self.object.creador_id:
                self.object.asignados.add(
                    self.object.creador_id
                )

            registrar_cambio_tarea(
                tarea=self.object,
                actor=self.request.user,
                anterior=anterior,
            )

        return HttpResponseRedirect(
            self.get_success_url()
        )


class TareaKanbanView(
    LoginRequiredMixin,
    TemplateView,
):
    template_name = "tareas/kanban.html"

    def get_context_data(
        self,
        **kwargs,
    ):
        context = super().get_context_data(
            **kwargs
        )

        context["tareas"] = (
            visible_tasks_for_user(
                self.request.user,
                active_team_id=(
                    _active_team_id(
                        self.request
                    )
                ),
                queryset=(
                    Tarea.objects
                    .select_related(
                        "team",
                        "creador",
                    )
                    .prefetch_related(
                        "asignados",
                    )
                ),
            )
            .order_by(
                "estado",
                "-creado",
            )
        )

        return context


@require_http_methods(["PATCH"])
@login_required
def api_detail(request, pk):
    tarea = get_object_or_404(
        editable_tasks_for_user(
            request.user,
            active_team_id=_active_team_id(request),
        ),
        pk=pk,
    )
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest("JSON inválido.")
    start = parse_datetime(str(payload.get("start") or ""))
    end_raw = payload.get("end")
    end = parse_datetime(str(end_raw)) if end_raw else None
    if start is None or (end_raw and end is None):
        return HttpResponseBadRequest("Fecha inválida.")
    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    if end is not None and timezone.is_naive(end):
        end = timezone.make_aware(end)
    if end is not None and end < start:
        return HttpResponseBadRequest("El fin no puede ser anterior al inicio.")
    anterior = snapshot_tarea(tarea)
    tarea.inicio_programado = start
    tarea.fin_programado = end
    tarea.vencimiento = timezone.localdate(start)
    with transaction.atomic():
        tarea.save(update_fields=[
            "inicio_programado", "fin_programado", "vencimiento", "actualizado"
        ])
        registrar_cambio_tarea(tarea=tarea, actor=request.user, anterior=anterior)
    return JsonResponse({"ok": True})


@require_http_methods(["POST"])
@login_required
def task_action(request, pk):
    tarea = get_object_or_404(
        editable_tasks_for_user(
            request.user,
            active_team_id=_active_team_id(request),
        ),
        pk=pk,
    )
    action = str(request.POST.get("action") or "").strip().lower()
    state_by_action = {"complete": "hecha", "reopen": "pendiente"}
    if action not in state_by_action:
        return HttpResponseBadRequest("Acción no válida.")
    anterior = snapshot_tarea(tarea)
    tarea.estado = state_by_action[action]
    with transaction.atomic():
        tarea.save(update_fields=["estado", "actualizado"])
        registrar_cambio_tarea(tarea=tarea, actor=request.user, anterior=anterior)
    return JsonResponse({"ok": True, "status": tarea.estado})
