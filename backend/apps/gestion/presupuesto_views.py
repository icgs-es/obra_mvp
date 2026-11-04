from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import PresupuestoProveedorGestion, PresupuestoVencimientoGestion
from .presupuesto_forms import PresupuestoForm, PresupuestoPlanFormSet
from .views import get_current_team_scope


def presupuestos_disponibles(request):
    scope, _, _ = get_current_team_scope(request)
    return PresupuestoProveedorGestion.objects.filter(team__in=scope)


@login_required
def presupuestos_list(request):
    presupuestos = presupuestos_disponibles(request).select_related("team", "proveedor", "obra")
    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    if q:
        presupuestos = presupuestos.filter(
            Q(numero_proveedor__icontains=q) | Q(concepto__icontains=q)
            | Q(proveedor__nombre_comercial__icontains=q) | Q(proveedor__nombre_fiscal__icontains=q)
            | Q(obra__nombre__icontains=q)
        )
    if estado in ("aprobado", "pendiente"):
        presupuestos = presupuestos.filter(aprobado_en__isnull=estado == "pendiente")
    page = Paginator(presupuestos, 30).get_page(request.GET.get("page"))
    return render(request, "gestion/presupuestos_list.html", {"page": page, "q": q, "estado": estado})


@login_required
def presupuesto_detail(request, pk):
    presupuesto = get_object_or_404(
        presupuestos_disponibles(request).select_related("team", "proveedor", "obra"), pk=pk,
    )
    vencimientos = list(presupuesto.vencimientos.all())
    previsto = sum((pago.importe_previsto for pago in vencimientos), Decimal("0.00"))
    pendiente = None if presupuesto.importe_total is None else presupuesto.importe_total - previsto
    return render(request, "gestion/presupuesto_detail.html", {
        "presupuesto": presupuesto, "vencimientos": vencimientos,
        "previsto": previsto, "pendiente": pendiente,
    })


@login_required
def presupuesto_form(request, pk=None):
    scope, team, modo_todas = get_current_team_scope(request)
    if pk is None:
        selected = request.POST.get("team_id") or request.GET.get("team_id")
        if selected:
            try:
                selected_id = int(selected)
            except ValueError as exc:
                raise Http404("Empresa no disponible.") from exc
            if not 0 < selected_id < 2**63:
                raise Http404("Empresa no disponible.")
            team = scope.filter(pk=selected_id).first()
        if team is None:
            raise Http404("Empresa no disponible.")
    is_post = request.method == "POST"
    with transaction.atomic():
        if pk is None:
            presupuesto = PresupuestoProveedorGestion(team=team)
        else:
            disponibles = presupuestos_disponibles(request)
            if is_post:
                disponibles = disponibles.select_for_update()
            presupuesto = get_object_or_404(disponibles, pk=pk)
            if presupuesto.aprobado:
                messages.error(request, "Revoca la aprobación para editar la ficha.")
                return redirect("gestion:presupuesto_detail", pk=pk)
        pdf_anterior = presupuesto.pdf.name
        form = PresupuestoForm(
            request.POST if is_post else None, request.FILES if is_post else None,
            team=presupuesto.team, instance=presupuesto,
        )
        if is_post and form.is_valid():
            presupuesto = form.save()
            if pdf_anterior and presupuesto.pdf.name != pdf_anterior:
                storage = presupuesto.pdf.storage
                transaction.on_commit(lambda: storage.delete(pdf_anterior), robust=True)
            messages.success(request, "Presupuesto guardado.")
            return redirect("gestion:presupuesto_detail", pk=presupuesto.pk)
    return render(request, "gestion/presupuesto_form.html", {
        "form": form, "presupuesto": presupuesto,
        "empresas": scope if pk is None and modo_todas else None,
    })


@login_required
@permission_required("gestion.approve_presupuesto", raise_exception=True)
@require_POST
def presupuesto_aprobacion(request, pk):
    accion = request.POST.get("accion")
    if accion not in ("aprobar", "revocar"):
        raise Http404()
    with transaction.atomic():
        presupuesto = get_object_or_404(presupuestos_disponibles(request).select_for_update(), pk=pk)
        aprobar = accion == "aprobar"
        if aprobar != presupuesto.aprobado:
            usuario = request.user
            presupuesto.aprobado_en = timezone.now() if aprobar else None
            presupuesto.aprobado_por = usuario if aprobar else None
            presupuesto.nombre_aprobador = (
                (usuario.get_full_name() or usuario.get_username())[:255] if aprobar else ""
            )
            presupuesto.save(update_fields=("aprobado_en", "aprobado_por", "nombre_aprobador"))
    return redirect("gestion:presupuesto_detail", pk=pk)


@login_required
@permission_required("gestion.authorize_factura_payment_plan", raise_exception=True)
def presupuesto_plan(request, pk):
    is_post = request.method == "POST"
    error = ""
    with transaction.atomic():
        disponibles = presupuestos_disponibles(request)
        if is_post:
            disponibles = disponibles.select_for_update()
        presupuesto = get_object_or_404(disponibles, pk=pk)
        campos = ("fecha_vencimiento", "hito", "importe_previsto", "forma_pago", "observaciones")
        inicial = list(presupuesto.vencimientos.values(*campos))
        formset = PresupuestoPlanFormSet(request.POST if is_post else None, initial=inicial, prefix="pagos")
        if is_post and formset.is_valid():
            pagos = [
                {campo: fila[campo] for campo in campos}
                for fila in formset.cleaned_data if fila and not fila.get("DELETE")
            ]
            previsto = sum(pago["importe_previsto"] for pago in pagos)
            if presupuesto.importe_total is not None and previsto > presupuesto.importe_total:
                error = "El importe planificado supera el total previsto del presupuesto."
            else:
                presupuesto.vencimientos.all().delete()
                PresupuestoVencimientoGestion.objects.bulk_create([
                    PresupuestoVencimientoGestion(presupuesto=presupuesto, **pago) for pago in pagos
                ])
                messages.success(request, "Plan de pagos previsto guardado.")
                return redirect("gestion:presupuesto_detail", pk=pk)
    return render(request, "gestion/presupuesto_plan.html", {
        "presupuesto": presupuesto, "formset": formset, "error": error,
    })


@login_required
def presupuesto_pdf(request, pk):
    presupuesto = get_object_or_404(presupuestos_disponibles(request), pk=pk)
    if not presupuesto.pdf:
        raise Http404()
    try:
        archivo = presupuesto.pdf.open("rb")
    except FileNotFoundError as exc:
        raise Http404() from exc
    return FileResponse(archivo, as_attachment=True, filename=f"presupuesto-{pk}.pdf")
