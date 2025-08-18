from datetime import date, datetime
import json
from django.db.models import Sum
from django.db.models.functions import TruncMonth, TruncWeek
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from .models import Obra, Planificacion
from .forms_extra import ParteTrabajoForm

def _pdate(s, default=None):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return default

@require_http_methods(["GET"])
def gantt(request):
    obra_id = request.GET.get("obra")
    ini = _pdate(request.GET.get("ini"), date.today().replace(day=1))
    fin = _pdate(request.GET.get("fin"), date.today())
    qs = (Planificacion.objects
          .select_related("tarea__capitulo__obra","recurso_personal","recurso_material")
          .filter(fecha__range=(ini, fin)))
    if obra_id:
        qs = qs.filter(tarea__capitulo__obra_id=obra_id)

    items, grupos = [], {}
    for p in qs:
        cap = p.tarea.capitulo
        label = (
            p.recurso_personal.nombre if p.recurso_personal
            else (p.recurso_material.nombre if p.recurso_material else p.tarea.nombre)
        )
        items.append({
            "id": p.id,
            "content": f"{label} · {p.tipo} · €{float(p.importe_plan or 0):.2f}",
            "start": p.fecha.isoformat(),
            "group": cap.codigo,
        })
        grupos[cap.codigo] = {"id": cap.codigo, "content": f"{cap.codigo} · {cap.nombre}"}

    context = {
        "obras": Obra.objects.all().order_by("codigo"),
        "obra_sel": int(obra_id) if obra_id else None,
        "ini": ini, "fin": fin,
        "items_json": json.dumps(items, ensure_ascii=False),
        "grupos_json": json.dumps(list(grupos.values()), ensure_ascii=False),
    }
    return render(request, "core/gantt.html", context)

@require_http_methods(["GET"])
def tesoreria(request):
    # Import perezoso para no romper si el modelo no existe
    try:
        from .models import Vencimiento
    except Exception:
        Vencimiento = None

    ini = _pdate(request.GET.get("ini"), date.today().replace(day=1))
    fin = _pdate(request.GET.get("fin"), date.today())
    periodo = request.GET.get("periodo", "mes")
    rows = []

    if Vencimiento is not None:
        key = TruncWeek("fecha_venc") if periodo == "semana" else TruncMonth("fecha_venc")
        rows = list(
            Vencimiento.objects.filter(fecha_venc__range=(ini, fin), pagado=False)
            .annotate(periodo=key).values("periodo")
            .annotate(importe=Sum("importe")).order_by("periodo")
        )

    # Prepara arrays JSON para Plotly (sin usar filtros de plantilla)
    x = []
    y = []
    for r in rows:
        per = r.get("periodo")
        if hasattr(per, "isoformat"):
            x.append(per.isoformat())
        elif per is not None:
            x.append(str(per))
        else:
            x.append(None)
        imp = r.get("importe") or 0
        try:
            y.append(float(imp))
        except Exception:
            y.append(0.0)

    context = {
        "ini": ini, "fin": fin, "periodo": periodo, "rows": rows,
        "x_json": json.dumps(x, ensure_ascii=False),
        "y_json": json.dumps(y, ensure_ascii=False),
    }
    return render(request, "core/tesoreria.html", context)

@require_http_methods(["GET","POST"])
def parte_alta(request):
    form = ParteTrabajoForm(request.POST or None)
    if request.method == "POST" and hasattr(form, "is_valid") and form.is_valid():
        if hasattr(form, "save"):
            form.save()
        return redirect("parte_alta")
    return render(request, "core/parte_alta.html", {"form": form})
