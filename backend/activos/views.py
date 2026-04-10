from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse

from .models import ActivoCore as Activo
from .forms import ActivoForm

try:
    from .models import ActivoActividad
except ImportError:
    ActivoActividad = None


@login_required
def activo_list(request):
    filtros = {
        "q": request.GET.get("q", "").strip(),
        "tipo": request.GET.get("tipo", "").strip(),
        "estado": request.GET.get("estado", "").strip(),
        "gestor": request.GET.get("gestor", "").strip(),
    }

    qs = Activo.objects.filter(team__in=request.user.teams.all())

    if filtros["q"]:
        qs = qs.filter(nombre__icontains=filtros["q"])

    if filtros["tipo"]:
        try:
            qs = qs.filter(tipo_activo=filtros["tipo"])
        except Exception:
            pass

    if filtros["estado"]:
        try:
            qs = qs.filter(estado_operativo=filtros["estado"])
        except Exception:
            pass

    # gestor: de momento no filtramos si no está claro el campo real
    activos = qs.order_by("-updated_at")

    tipo_choices = []
    estado_choices = []
    gestor_choices = []

    try:
        tipo_choices = Activo._meta.get_field("tipo_activo").choices or []
    except Exception:
        tipo_choices = []

    try:
        estado_choices = Activo._meta.get_field("estado_operativo").choices or []
    except Exception:
        estado_choices = []

    activo_seleccionado = None
    actividades_activas = []

    activo_id = request.GET.get("activo")
    if activo_id:
        activo_seleccionado = (
            Activo.objects
            .filter(team__in=request.user.teams.all(), pk=activo_id)
            .first()
        )

        if activo_seleccionado and ActivoActividad is not None:
            actividades_activas = (
                ActivoActividad.objects
                .filter(activo=activo_seleccionado, completada=False)
                .order_by("-id")
            )

    context = {
        "activos": activos,
        "activo_seleccionado": activo_seleccionado,
        "actividades_activas": actividades_activas,
        "filtros": filtros,
        "total_resultados": activos.count(),
        "tipo_choices": tipo_choices,
        "estado_choices": estado_choices,
        "gestor_choices": gestor_choices,
    }
    return render(request, "activos/activo_list.html", context)


@login_required
def activo_create(request):
    if request.method == "POST":
        form = ActivoForm(request.POST)
        if form.is_valid():
            activo = form.save(commit=False)
            team = request.user.teams.first()
            if team:
                activo.team = team
            activo.save()
            return redirect(reverse("activos:detail", kwargs={"pk": activo.pk}))
    else:
        form = ActivoForm()

    return render(request, "activos/activo_form.html", {"form": form})


@login_required
def activo_detail(request, pk):
    activo = get_object_or_404(
        Activo,
        pk=pk,
        team__in=request.user.teams.all(),
    )
    return render(request, "activos/activo_detail.html", {"activo": activo})


@login_required
def activo_update(request, pk):
    activo = get_object_or_404(
        Activo,
        pk=pk,
        team__in=request.user.teams.all(),
    )

    if request.method == "POST":
        form = ActivoForm(request.POST, instance=activo)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.team = activo.team
            obj.save()
            return redirect(reverse("activos:detail", kwargs={"pk": activo.pk}))
    else:
        form = ActivoForm(instance=activo)

    return render(
        request,
        "activos/activo_form.html",
        {"form": form, "activo": activo},
    )


@login_required
def activo_delete(request, pk):
    activo = get_object_or_404(
        Activo,
        pk=pk,
        team__in=request.user.teams.all(),
    )

    if request.method == "POST":
        activo.delete()
        return redirect(reverse("activos:list"))

    return render(
        request,
        "activos/activo_confirm_delete.html",
        {"activo": activo},
    )