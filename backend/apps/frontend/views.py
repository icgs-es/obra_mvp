
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.forms import ModelForm
from django.http import HttpRequest, HttpResponse
from django.db.models import Q

from apps.core.models import Obra, SubObra, Capitulo, Tarea

# -------- Helpers --------
def _get_int(request: HttpRequest, name: str):
    val = request.GET.get(name) or request.POST.get(name)
    try:
        return int(val) if val not in (None, "", "0") else None
    except ValueError:
        return None

# -------- Health ---------
@require_http_methods(["GET"])
def ping(request: HttpRequest):
    return HttpResponse("tabs ok")

# -------- Forms ----------
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
        model = Tarea  # Tarea ≈ Partida
        fields = ["capitulo", "nombre"]

# -------- Tabs Home ------
@require_http_methods(["GET"])
def tabs_home(request: HttpRequest):
    return render(request, "frontend/tabs.html")

# -------- TAB Obras ------
@require_http_methods(["GET", "POST"])
def tab_obras(request: HttpRequest):
    if request.method == "POST":
        form = ObraForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("tab_obras")
    else:
        form = ObraForm()

    q = request.GET.get("q", "").strip()
    obras = Obra.objects.all()
    if q:
        obras = obras.filter(Q(codigo__icontains=q) | Q(nombre__icontains=q))
    obras = obras.order_by("codigo", "id")
    return render(request, "frontend/partials/obras_tab.html", {"form": form, "rows": obras, "q": q})

@require_http_methods(["GET"])
def obra_row(request: HttpRequest, pk: int):
    row = get_object_or_404(Obra, pk=pk)
    return render(request, "frontend/partials/rows/obra.html", {"r": row})

@require_http_methods(["GET", "POST"])
def obra_edit(request: HttpRequest, pk: int):
    row = get_object_or_404(Obra, pk=pk)
    if request.method == "POST":
        form = ObraForm(request.POST, instance=row)
        if form.is_valid():
            form.save()
            return obra_row(request, pk)
    else:
        form = ObraForm(instance=row)
    return render(request, "frontend/partials/rows/obra_edit.html", {"form": form, "r": row})

@require_http_methods(["POST"])
def obra_delete(request: HttpRequest, pk: int):
    row = get_object_or_404(Obra, pk=pk)
    row.delete()
    return redirect("tab_obras")

# -------- TAB SubObras ---
@require_http_methods(["GET", "POST"])
def tab_subobras(request: HttpRequest):
    obra_id = _get_int(request, "obra")

    if request.method == "POST":
        form = SubObraForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("tab_subobras")
    else:
        form = SubObraForm()

    obras = Obra.objects.all().order_by("codigo")

    subobras_qs = SubObra.objects.select_related("obra").all()
    if obra_id:
        subobras_qs = subobras_qs.filter(obra_id=obra_id)
    subobras_qs = subobras_qs.order_by("obra__codigo", "codigo", "id")

    ctx = {
        "form": form,
        "rows": subobras_qs,
        "subobras": subobras_qs,  # compat
        "obras": obras,
        "obra_id": obra_id,
    }
    return render(request, "frontend/partials/subobras_tab.html", ctx)

@require_http_methods(["GET"])
def subobra_row(request: HttpRequest, pk: int):
    row = get_object_or_404(SubObra, pk=pk)
    return render(request, "frontend/partials/rows/subobra.html", {"r": row})

@require_http_methods(["GET", "POST"])
def subobra_edit(request: HttpRequest, pk: int):
    row = get_object_or_404(SubObra, pk=pk)
    if request.method == "POST":
        form = SubObraForm(request.POST, instance=row)
        if form.is_valid():
            form.save()
            return subobra_row(request, pk)
    else:
        form = SubObraForm(instance=row)
    return render(request, "frontend/partials/rows/subobra_edit.html", {"form": form, "r": row})

@require_http_methods(["POST"])
def subobra_delete(request: HttpRequest, pk: int):
    row = get_object_or_404(SubObra, pk=pk)
    row.delete()
    return redirect("tab_subobras")

# -------- TAB Capítulos --
@require_http_methods(["GET", "POST"])
def tab_capitulos(request: HttpRequest):
    obra_id = _get_int(request, "obra")
    subobra_id = _get_int(request, "subobra")

    if request.method == "POST":
        form = CapituloForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("tab_capitulos")
    else:
        form = CapituloForm()

    obras = Obra.objects.all().order_by("codigo")

    subobras_qs = SubObra.objects.select_related("obra")
    if obra_id:
        subobras_qs = subobras_qs.filter(obra_id=obra_id)
    subobras_qs = subobras_qs.order_by("obra__codigo", "codigo")

    capitulos = Capitulo.objects.select_related("obra", "subobra").all()
    if obra_id:
        capitulos = capitulos.filter(obra_id=obra_id)
    if subobra_id:
        capitulos = capitulos.filter(subobra_id=subobra_id)
    capitulos = capitulos.order_by("obra__codigo", "subobra__codigo", "codigo", "id")

    ctx = {
        "form": form, "rows": capitulos,
        "obras": obras, "subobras": subobras_qs,
        "obra_id": obra_id, "subobra_id": subobra_id
    }
    return render(request, "frontend/partials/capitulos_tab.html", ctx)

@require_http_methods(["GET"])
def capitulo_row(request: HttpRequest, pk: int):
    row = get_object_or_404(Capitulo, pk=pk)
    return render(request, "frontend/partials/rows/capitulo.html", {"r": row})

@require_http_methods(["GET", "POST"])
def capitulo_edit(request: HttpRequest, pk: int):
    row = get_object_or_404(Capitulo, pk=pk)
    if request.method == "POST":
        form = CapituloForm(request.POST, instance=row)
        if form.is_valid():
            form.save()
            return capitulo_row(request, pk)
    else:
        form = CapituloForm(instance=row)
    return render(request, "frontend/partials/rows/capitulo_edit.html", {"form": form, "r": row})

@require_http_methods(["POST"])
def capitulo_delete(request: HttpRequest, pk: int):
    row = get_object_or_404(Capitulo, pk=pk)
    row.delete()
    return redirect("tab_capitulos")

# -------- TAB Partidas ----
@require_http_methods(["GET", "POST"])
def tab_partidas(request: HttpRequest):
    obra_id = _get_int(request, "obra")
    subobra_id = _get_int(request, "subobra")
    capitulo_id = _get_int(request, "capitulo")

    if request.method == "POST":
        form = PartidaForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("tab_partidas")
    else:
        form = PartidaForm()

    obras = Obra.objects.all().order_by("codigo")

    subobras_qs = SubObra.objects.select_related("obra")
    if obra_id:
        subobras_qs = subobras_qs.filter(obra_id=obra_id)
    subobras_qs = subobras_qs.order_by("obra__codigo", "codigo")

    capitulos_qs = Capitulo.objects.select_related("obra", "subobra")
    if obra_id:
        capitulos_qs = capitulos_qs.filter(obra_id=obra_id)
    if subobra_id:
        capitulos_qs = capitulos_qs.filter(subobra_id=subobra_id)
    capitulos_qs = capitulos_qs.order_by("obra__codigo", "subobra__codigo", "codigo")

    partidas = Tarea.objects.select_related("capitulo", "capitulo__obra", "capitulo__subobra").all()
    if capitulo_id:
        partidas = partidas.filter(capitulo_id=capitulo_id)
    else:
        if obra_id:
            partidas = partidas.filter(capitulo__obra_id=obra_id)
        if subobra_id:
            partidas = partidas.filter(capitulo__subobra_id=subobra_id)
    partidas = partidas.order_by("capitulo__obra__codigo", "capitulo__subobra__codigo", "capitulo__codigo", "nombre", "id")

    ctx = {
        "form": form, "rows": partidas,
        "obras": obras, "subobras": subobras_qs, "capitulos": capitulos_qs,
        "obra_id": obra_id, "subobra_id": subobra_id, "capitulo_id": capitulo_id
    }
    return render(request, "frontend/partials/partidas_tab.html", ctx)

@require_http_methods(["GET"])
def partida_row(request: HttpRequest, pk: int):
    row = get_object_or_404(Tarea, pk=pk)
    return render(request, "frontend/partials/rows/partida.html", {"r": row})

@require_http_methods(["GET", "POST"])
def partida_edit(request: HttpRequest, pk: int):
    row = get_object_or_404(Tarea, pk=pk)
    if request.method == "POST":
        form = PartidaForm(request.POST, instance=row)
        if form.is_valid():
            form.save()
            return partida_row(request, pk)
    else:
        form = PartidaForm(instance=row)
    return render(request, "frontend/partials/rows/partida_edit.html", {"form": form, "r": row})

@require_http_methods(["POST"])
def partida_delete(request: HttpRequest, pk: int):
    row = get_object_or_404(Tarea, pk=pk)
    row.delete()
    return redirect("tab_partidas")
