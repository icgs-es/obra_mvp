from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Lead, FuenteLead
from .serializers import LeadSerializer
from .services.import_excel import preview_import, commit_import
from .forms import LeadForm, ImportLeadsForm

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, FormView
from django.core.exceptions import PermissionDenied
from django.urls import reverse_lazy
import csv
from io import TextIOWrapper


@login_required
def crm_index(request):
    return render(request, "crm/index.html")


@login_required
def set_active_team(request, team_id):
    if team_id == 0:
        request.session["active_team_id"] = "all"
    elif request.user.teams.filter(id=team_id).exists():
        request.session["active_team_id"] = team_id
    return redirect(request.META.get("HTTP_REFERER", "crm:index"))


class CRMTeamMixin:
    def get_active_team(self):
        teams = self.request.user.teams.all()
        team_id = self.request.session.get("active_team_id")
        if team_id == "all":
            return None
        if team_id and teams.filter(id=team_id).exists():
            return teams.get(id=team_id)
        return teams.first()


class LeadListView(LoginRequiredMixin, CRMTeamMixin, ListView):
    model = Lead
    template_name = "crm/lead_list.html"

    def get_queryset(self):
        active_team = self.get_active_team()
        if active_team is None:
            qs = Lead.objects.filter(team__in=self.request.user.teams.all())
        else:
            qs = Lead.objects.filter(team=active_team)

        fuente_id = self.request.GET.get("fuente") or ""
        activo_filter = self.request.GET.get("activo") or "todos"

        if fuente_id:
            qs = qs.filter(fuente_id=fuente_id)

        if activo_filter == "activos":
            qs = qs.filter(activo_lead=True)
        elif activo_filter == "inactivos":
            qs = qs.filter(activo_lead=False)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_team = self.get_active_team()
        if active_team is None:
            context["fuentes"] = (
                FuenteLead.objects.filter(team__in=self.request.user.teams.all())
                .order_by("nombre")
                .distinct()
            )
        else:
            context["fuentes"] = (
                FuenteLead.objects.filter(team=active_team)
                .order_by("nombre")
                .distinct()
            )
        context["filtro_fuente"] = self.request.GET.get("fuente", "")
        context["filtro_activo"] = self.request.GET.get("activo", "todos")
        return context


class LeadCreateView(LoginRequiredMixin, CRMTeamMixin, CreateView):
    model = Lead
    template_name = "crm/lead_form.html"
    form_class = LeadForm
    success_url = reverse_lazy("crm:lead_list")

    def form_valid(self, form):
        teams = self.request.user.teams.all()
        if not teams.exists():
            raise PermissionDenied("El usuario no tiene equipos asignados")
        form.instance.team = self.get_active_team()
        form.instance.agente = self.request.user
        return super().form_valid(form)


class LeadUpdateView(LoginRequiredMixin, UpdateView):
    model = Lead
    template_name = "crm/lead_form.html"
    form_class = LeadForm
    success_url = reverse_lazy("crm:lead_list")

    def get_queryset(self):
        return Lead.objects.filter(team__in=self.request.user.teams.all())


class LeadDeleteView(LoginRequiredMixin, DeleteView):
    model = Lead
    template_name = "crm/lead_confirm_delete.html"
    success_url = reverse_lazy("crm:lead_list")

    def get_queryset(self):
        return Lead.objects.filter(team__in=self.request.user.teams.all())


class ImportLeadsView(LoginRequiredMixin, CRMTeamMixin, FormView):
    template_name = "crm/lead_import.html"
    form_class = ImportLeadsForm
    success_url = reverse_lazy("crm:lead_list")

    def form_valid(self, form):
        teams = self.request.user.teams.all()
        if not teams.exists():
            raise PermissionDenied("El usuario no tiene equipos asignados")
        
        team = self.get_active_team()

        if not team:
            raise PermissionDenied("No hay equipo activo")
        
        file = form.cleaned_data["file"]
        # Asumimos CSV en UTF-8 con cabecera nombre,email,telefono
        wrapped = TextIOWrapper(file.file, encoding="utf-8")
        reader = csv.DictReader(wrapped)

        existentes = set(
            Lead.objects.filter(team=team)
            .exclude(email="")
            .values_list("email", flat=True)
        )
        nuevos_emails = set()

        creados = 0
        ignorados = 0

        for row in reader:
            nombre = (row.get("nombre") or "").strip()
            email = (row.get("email") or "").strip().lower()
            telefono = (row.get("telefono") or "").strip()

            if not nombre:
                ignorados += 1
                continue

            if email:
                if email in existentes or email in nuevos_emails:
                    ignorados += 1
                    continue

            lead_kwargs = {
                "team": team,
                "nombre": nombre,
                "email": email,
                "telefono": telefono,
            }

            try:
                lead = Lead.objects.create(**lead_kwargs)
            except Exception:
                ignorados += 1
                continue

            creados += 1
            if email:
                nuevos_emails.add(email)

        # Pasamos resumen al template usando context extra
        context = self.get_context_data(form=form, creados=creados, ignorados=ignorados)
        return self.render_to_response(context)


class LeadViewSet(viewsets.ModelViewSet):
    serializer_class = LeadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Lead.objects.filter(team__in=self.request.user.teams.all())

    @action(detail=False, methods=["post"], url_path="import/preview")
    def import_preview(self, request, *args, **kwargs):
        file = request.FILES.get("file")
        team_id = request.data.get("team_id")
        if not file or not team_id:
            return Response({"error": "Falta fichero Excel o team_id"}, status=400)
        datos = preview_import(file, team_id)
        return Response(datos)

    @action(detail=False, methods=["post"], url_path="import/commit")
    def import_commit(self, request, *args, **kwargs):
        file = request.FILES.get("file")
        team_id = request.data.get("team_id")
        if not file or not team_id:
            return Response({"error": "Falta fichero Excel o team_id"}, status=400)
        datos = commit_import(file, team_id)
        return Response(datos)