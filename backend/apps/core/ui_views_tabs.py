# backend/apps/core/ui_views_tabs.py
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.forms import ModelForm
from django.http import HttpRequest
from django.contrib.auth.decorators import login_required

from .models import Obra, SubObra, Capitulo, Tarea
from .auth import require_constructora  # decorador de permisos


# ==== Formularios mínimos ====
class ObraForm(ModelForm):
    class Meta:
        model = Obra
        fields = ["codigo", "nombre"]

class SubObraForm(ModelForm):
    class Meta:
        model = SubObra
        fields = ["obra", "codigo", "nombre"]

class CapituloForm(ModelForm):
    class Meta:
        model = Capitulo
        fields = ["obra", "subobra", "codigo", "nombre"]

class PartidaForm(ModelForm):
    class Meta:
        model = Tarea  # mostramos Tarea como Partida
        fields = ["capitulo", "nombre"]


# ==== Home de pestañas (página completa) ====
@require_http_methods(["GET"])
@login_required
@require_constructora
def tabs_home(request: HttpRequest):
    # IMPORTANTE: el template debe estar en templates/core/tabs.html
    return render(request, "core/tabs.html")


# ==== Parciales HTMX ====
@require_http_methods(["GET", "POST"])
@login_required
@require_constructora
def tab_obras(request: HttpRequest):
    if request.method == "POST":
        form = ObraForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("construccion:tab_obras")
    else:
        form = ObraForm()
    qs = Obra.objects.all().order_by("codigo", "id")
    return render(request, "core/partials/obras_tab.html", {"form": form, "rows": qs, "obras": qs})

@require_http_methods(["GET", "POST"])
@login_required
@require_constructora
def tab_subobras(request: HttpRequest):
    if request.method == "POST":
        form = SubObraForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("construccion:tab_subobras")
    else:
        form = SubObraForm()
    qs = SubObra.objects.select_related("obra").all().order_by("obra__codigo", "codigo", "id")
    return render(request, "core/partials/subobras_tab.html", {"form": form, "rows": qs, "subobras": qs})

@require_http_methods(["GET", "POST"])
@login_required
@require_constructora
def tab_capitulos(request: HttpRequest):
    if request.method == "POST":
        form = CapituloForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("construccion:tab_capitulos")
    else:
        form = CapituloForm()
    qs = (
        Capitulo.objects.select_related("obra", "subobra")
        .all()
        .order_by("obra__codigo", "subobra__codigo", "codigo", "id")
    )
    return render(request, "core/partials/capitulos_tab.html", {"form": form, "rows": qs, "capitulos": qs})

@require_http_methods(["GET", "POST"])
@login_required
@require_constructora
def tab_partidas(request: HttpRequest):
    if request.method == "POST":
        form = PartidaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("construccion:tab_partidas")
    else:
        form = PartidaForm()
    qs = (
        Tarea.objects.select_related("capitulo", "capitulo__obra", "capitulo__subobra")
        .all()
        .order_by(
            "capitulo__obra__codigo",
            "capitulo__subobra__codigo",
            "capitulo__codigo",
            "nombre",
            "id",
        )
    )
    return render(request, "core/partials/partidas_tab.html", {"form": form, "rows": qs, "partidas": qs})
