from decimal import Decimal

from django import forms
from django.utils import timezone

from planificacion_obra.models import (
    AlmacenObra,
    RecursoCatalogo,
)
from planificacion_obra.utils import get_active_team


def _apply_mobile_team_scope(qs, request):
    user = getattr(request, "user", None)
    active_team = None
    active_team_id = None

    if request is not None:
        try:
            active_team_id = request.session.get("active_team_id")
        except Exception:
            active_team_id = None

        if active_team_id not in (None, "", "all"):
            active_team = get_active_team(request)

    if active_team is not None:
        return qs.filter(team=active_team)

    if user is not None and not getattr(user, "is_superuser", False) and hasattr(user, "teams"):
        return qs.filter(team__in=user.teams.all())

    return qs


class StockMovilFiltroForm(forms.Form):
    q = forms.CharField(
        label="Buscar",
        required=False,
        max_length=120,
    )
    tipo = forms.ChoiceField(
        label="Tipo",
        required=False,
        choices=[("", "Todos")],
    )
    almacen = forms.ModelChoiceField(
        queryset=AlmacenObra.objects.none(),
        label="Último movimiento en almacén",
        required=False,
    )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)

        almacenes = _apply_mobile_team_scope(
            AlmacenObra.objects.select_related("team", "obra"), request
        )

        recursos = _apply_mobile_team_scope(
            RecursoCatalogo.objects.filter(control_stock=True), request
        )

        tipos = (
            recursos
            .exclude(tipo="")
            .values_list("tipo", flat=True)
            .distinct()
            .order_by("tipo")
        )

        self.fields["tipo"].choices = [("", "Todos")] + [(t, t) for t in tipos]
        self.fields["almacen"].queryset = almacenes.order_by(
            "obra__legacy_cod_obra",
            "legacy_id_almacen",
            "nombre",
            "id",
        )
        self.fields["almacen"].label_from_instance = self._label_almacen

        self.fields["q"].widget.attrs.setdefault("class", "form-control form-control-lg")
        self.fields["q"].widget.attrs.setdefault("placeholder", "Código o texto")
        self.fields["tipo"].widget.attrs.setdefault("class", "form-select form-select-lg")
        self.fields["almacen"].widget.attrs.setdefault("class", "form-select form-select-lg")

    def _label_almacen(self, obj):
        return " · ".join(str(x) for x in [
            getattr(obj.obra, "legacy_cod_obra", None),
            getattr(obj.obra, "nombre", None),
            obj.legacy_id_almacen,
            obj.nombre,
        ] if x not in ("", None))


class ControlStockMovilForm(forms.Form):
    almacen = forms.ModelChoiceField(
        queryset=AlmacenObra.objects.none(),
        label="Almacén",
        required=True,
    )
    recurso = forms.ModelChoiceField(
        queryset=RecursoCatalogo.objects.none(),
        label="Recurso",
        required=True,
    )
    stock_contado = forms.DecimalField(
        label="Stock contado",
        required=True,
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=4,
    )
    unidad = forms.CharField(
        label="Unidad",
        required=False,
        max_length=40,
    )
    fecha_movimiento = forms.DateField(
        label="Fecha conteo",
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=timezone.localdate,
    )
    hora_movimiento = forms.TimeField(
        label="Hora",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, request=None, recurso_pk=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request

        almacenes = _apply_mobile_team_scope(
            AlmacenObra.objects.select_related("team", "obra"), request
        )
        recursos = _apply_mobile_team_scope(
            RecursoCatalogo.objects.select_related("team", "capitulo").filter(control_stock=True), request
        )

        recurso_obj = None
        selected_recurso_id = None

        if self.is_bound:
            selected_recurso_id = self.data.get("recurso") or None
        elif recurso_pk:
            selected_recurso_id = str(recurso_pk)

        if selected_recurso_id:
            recurso_obj = recursos.filter(pk=selected_recurso_id).first()

        if recurso_obj is not None:
            almacenes = almacenes.filter(team=recurso_obj.team)
            if not self.is_bound:
                self.initial.setdefault("recurso", recurso_obj.pk)
                self.initial.setdefault("unidad", recurso_obj.unidad or "")
                self.initial.setdefault("stock_contado", recurso_obj.stock if recurso_obj.stock is not None else Decimal("0"))

        self.fields["almacen"].queryset = almacenes.order_by(
            "obra__legacy_cod_obra",
            "legacy_id_almacen",
            "nombre",
            "id",
        )
        self.fields["recurso"].queryset = recursos.order_by("tipo", "nombre", "legacy_id", "id")

        self.fields["almacen"].label_from_instance = self._label_almacen
        self.fields["recurso"].label_from_instance = self._label_recurso

        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select form-select-lg")
            else:
                widget.attrs.setdefault("class", "form-control form-control-lg")

        self.fields["stock_contado"].widget.attrs.setdefault("step", "0.0001")
        self.fields["unidad"].widget.attrs.setdefault("placeholder", "UD, SACO, CUBAS, L...")
        self.fields["observaciones"].widget.attrs.setdefault("placeholder", "Motivo del conteo o ajuste")

    def _label_almacen(self, obj):
        return " · ".join(str(x) for x in [
            getattr(obj.obra, "legacy_cod_obra", None),
            getattr(obj.obra, "nombre", None),
            obj.legacy_id_almacen,
            obj.nombre,
        ] if x not in ("", None))

    def _label_recurso(self, obj):
        return " · ".join(str(x) for x in [
            obj.tipo,
            obj.legacy_id,
            obj.nombre,
            obj.unidad,
            f"Stock actual: {obj.stock}" if obj.stock is not None else "Stock actual: -",
        ] if x not in ("", None))

    def clean(self):
        cleaned = super().clean()

        almacen = cleaned.get("almacen")
        recurso = cleaned.get("recurso")
        stock_contado = cleaned.get("stock_contado")
        unidad = (cleaned.get("unidad") or "").strip()
        fecha = cleaned.get("fecha_movimiento")

        if fecha and fecha > timezone.localdate():
            self.add_error("fecha_movimiento", "No se puede registrar un control de stock con fecha futura.")

        if stock_contado is not None and stock_contado < 0:
            self.add_error("stock_contado", "El stock contado no puede ser negativo.")

        if almacen and recurso and recurso.team_id != almacen.team_id:
            self.add_error("recurso", "El recurso no pertenece a la misma empresa que el almacén.")

        if recurso and not unidad:
            cleaned["unidad"] = recurso.unidad or ""

        return cleaned
