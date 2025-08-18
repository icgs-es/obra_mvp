
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods
from django.forms import ModelForm
from django.http import HttpRequest
from .models import Obra, SubObra, Capitulo, Tarea

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

# ==== Home de pestañas ====
@require_http_methods(["GET"])
def tabs_home(request: HttpRequest):
    return render(request, "core/tabs.html")

# ==== Parciales HTMX ====
@require_http_methods(["GET", "POST"])
def tab_obras(request: HttpRequest):
    if request.method == "POST":
        form = ObraForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("tab_obras")
    else:
        form = ObraForm()
    obras = Obra.objects.all().order_by("codigo", "id")
    return render(request, "core/partials/obras_tab.html", {"form": form, "rows": obras})

@require_http_methods(["GET", "POST"])
def tab_subobras(request: HttpRequest):
    if request.method == "POST":
        form = SubObraForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("tab_subobras")
    else:
        form = SubObraForm()
    subobras = SubObra.objects.select_related("obra").all().order_by("obra__codigo", "codigo", "id")
    return render(request, "core/partials/subobras_tab.html", {"form": form, "rows": subobras})

@require_http_methods(["GET", "POST"])
def tab_capitulos(request: HttpRequest):
    if request.method == "POST":
        form = CapituloForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("tab_capitulos")
    else:
        form = CapituloForm()
    capitulos = (Capitulo.objects
                 .select_related("obra", "subobra")
                 .all().order_by("obra__codigo", "subobra__codigo", "codigo", "id"))
    return render(request, "core/partials/capitulos_tab.html", {"form": form, "rows": capitulos})

@require_http_methods(["GET", "POST"])
def tab_partidas(request: HttpRequest):
    if request.method == "POST":
        form = PartidaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("tab_partidas")
    else:
        form = PartidaForm()
    partidas = (Tarea.objects
                .select_related("capitulo", "capitulo__obra", "capitulo__subobra")
                .all().order_by("capitulo__obra__codigo", "capitulo__subobra__codigo", "capitulo__codigo", "nombre", "id"))
    return render(request, "core/partials/partidas_tab.html", {"form": form, "rows": partidas})
