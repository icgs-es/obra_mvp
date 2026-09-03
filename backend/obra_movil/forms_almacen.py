from decimal import Decimal

from django import forms
from django.db.models import Q
from django.utils import timezone

from planificacion_obra.models import (
    AlmacenObra,
    EmpleadoObra,
    PartidaCatalogo,
    RecursoCatalogo,
    UnidadObra,
)
from planificacion_obra.utils import get_active_team


TIPO_MOVIMIENTO_CHOICES = [
    ("ENTRADA", "Entrada"),
    ("SALIDA", "Salida"),
    ("CONTROL_STOCK", "Control stock"),
    ("ROTURA", "Rotura"),
]


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


def _posted(data, key):
    if not data:
        return None
    value = data.get(key)
    return value if value not in ("", None) else None


class AlmacenMovimientoFiltroForm(forms.Form):
    f_almacen = forms.ModelChoiceField(
        queryset=AlmacenObra.objects.none(),
        label="Almacén",
        required=False,
    )
    q_recurso = forms.CharField(
        label="Buscar recurso",
        required=False,
        max_length=120,
    )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)

        almacenes = _apply_mobile_team_scope(
            AlmacenObra.objects.select_related("team", "obra"), request
        )

        self.fields["f_almacen"].queryset = almacenes.order_by(
            "obra__legacy_cod_obra",
            "legacy_id_almacen",
            "nombre",
            "id",
        )
        self.fields["f_almacen"].label_from_instance = self._label_almacen

        self.fields["f_almacen"].widget.attrs.setdefault("class", "form-select form-select-lg")
        self.fields["q_recurso"].widget.attrs.setdefault("class", "form-control form-control-lg")
        self.fields["q_recurso"].widget.attrs.setdefault("placeholder", "Código o texto del recurso")

    def _label_almacen(self, obj):
        return " · ".join(str(x) for x in [
            getattr(obj.obra, "legacy_cod_obra", None),
            getattr(obj.obra, "nombre", None),
            obj.legacy_id_almacen,
            obj.nombre,
        ] if x not in ("", None))


class AlmacenMovimientoMovilForm(forms.Form):
    almacen = forms.ModelChoiceField(
        queryset=AlmacenObra.objects.none(),
        label="Almacén",
        required=True,
    )
    tipo_movimiento = forms.ChoiceField(
        choices=TIPO_MOVIMIENTO_CHOICES,
        label="Tipo",
        required=True,
        widget=forms.RadioSelect,
        initial="SALIDA",
    )
    recurso = forms.ModelChoiceField(
        queryset=RecursoCatalogo.objects.none(),
        label="Recurso",
        required=True,
    )
    cantidad = forms.DecimalField(
        label="Cantidad",
        required=True,
        min_value=Decimal("0.0001"),
        max_digits=14,
        decimal_places=4,
    )
    unidad = forms.CharField(
        label="Unidad",
        required=False,
        max_length=40,
    )
    fecha_movimiento = forms.DateField(
        label="Fecha",
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=timezone.localdate,
    )
    hora_movimiento = forms.TimeField(
        label="Hora",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    unidad_obra = forms.ModelChoiceField(
        queryset=UnidadObra.objects.none(),
        label="Vivienda / unidad",
        required=False,
    )
    partida = forms.ModelChoiceField(
        queryset=PartidaCatalogo.objects.none(),
        label="Partida",
        required=False,
    )
    empleado = forms.ModelChoiceField(
        queryset=EmpleadoObra.objects.none(),
        label="Empleado",
        required=False,
    )
    vehiculo = forms.CharField(
        label="Vehículo",
        required=False,
        max_length=80,
    )
    kilometraje = forms.DecimalField(
        label="Kilometraje",
        required=False,
        min_value=Decimal("0"),
        max_digits=12,
        decimal_places=2,
    )
    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, request=None, filters=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.recursos_limitados = False

        data = self.data if self.is_bound else None
        filters = filters or data

        almacenes = _apply_mobile_team_scope(
            AlmacenObra.objects.select_related("team", "obra"), request
        )
        recursos = _apply_mobile_team_scope(
            RecursoCatalogo.objects.select_related("team", "capitulo").filter(control_stock=True), request
        )
        unidades = _apply_mobile_team_scope(
            UnidadObra.objects.select_related("team", "obra"), request
        )
        partidas = _apply_mobile_team_scope(
            PartidaCatalogo.objects.select_related("team", "capitulo"), request
        )
        empleados = _apply_mobile_team_scope(
            EmpleadoObra.objects.select_related("team").filter(situacion=EmpleadoObra.Situacion.ACTIVO), request
        )

        almacen_id = _posted(data, "almacen") or _posted(filters, "f_almacen")
        q_recurso = (_posted(filters, "q_recurso") or "").strip()
        almacen_obj = None

        if almacen_id:
            almacen_obj = almacenes.filter(pk=almacen_id).first()

        if almacen_obj is not None:
            recursos = recursos.filter(team=almacen_obj.team)
            unidades = unidades.filter(obra=almacen_obj.obra)
            partidas = partidas.filter(team=almacen_obj.team)
            empleados = empleados.filter(team=almacen_obj.team)

            if not self.is_bound:
                self.initial.setdefault("almacen", almacen_obj.pk)

        if q_recurso:
            q = Q(nombre__icontains=q_recurso)
            if q_recurso.isdigit():
                q |= Q(legacy_id=int(q_recurso))
            recursos = recursos.filter(q)

        recursos = recursos.order_by("tipo", "nombre", "legacy_id", "id")

        if not q_recurso and not self.is_bound:
            self.recursos_limitados = True
            recursos = recursos[:250]

        self.fields["almacen"].queryset = almacenes.order_by("obra__legacy_cod_obra", "legacy_id_almacen", "nombre", "id")
        self.fields["recurso"].queryset = recursos
        self.fields["unidad_obra"].queryset = unidades.order_by("obra__legacy_cod_obra", "edificio", "vivienda", "nivel", "id")
        self.fields["partida"].queryset = partidas.order_by("capitulo__codigo", "codigo", "nombre", "id")
        self.fields["empleado"].queryset = empleados.order_by("nombre", "id")

        self.fields["almacen"].label_from_instance = self._label_almacen
        self.fields["recurso"].label_from_instance = self._label_recurso
        self.fields["unidad_obra"].label_from_instance = self._label_unidad
        self.fields["partida"].label_from_instance = lambda obj: f"{obj.codigo} · {obj.nombre}"
        self.fields["empleado"].label_from_instance = lambda obj: obj.nombre or str(obj)

        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.RadioSelect):
                widget.attrs.setdefault("class", "obra-mobile-radio")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select form-select-lg")
            else:
                widget.attrs.setdefault("class", "form-control form-control-lg")

        self.fields["cantidad"].widget.attrs.setdefault("step", "0.0001")
        self.fields["kilometraje"].widget.attrs.setdefault("step", "0.01")
        self.fields["unidad"].widget.attrs.setdefault("placeholder", "UD, SACO, CUBAS, L...")
        self.fields["observaciones"].widget.attrs.setdefault("placeholder", "Nota opcional desde obra")

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
            f"Stock: {obj.stock}" if obj.stock is not None else "Stock: -",
        ] if x not in ("", None))

    def _label_unidad(self, obj):
        return " · ".join(str(x) for x in [
            getattr(obj.obra, "nombre", None),
            obj.edificio,
            obj.vivienda,
            obj.nivel,
        ] if x not in ("", None))

    def clean(self):
        cleaned = super().clean()

        almacen = cleaned.get("almacen")
        recurso = cleaned.get("recurso")
        tipo = cleaned.get("tipo_movimiento")
        cantidad = cleaned.get("cantidad")
        unidad = (cleaned.get("unidad") or "").strip()
        fecha = cleaned.get("fecha_movimiento")
        unidad_obra = cleaned.get("unidad_obra")
        partida = cleaned.get("partida")
        empleado = cleaned.get("empleado")

        if fecha and fecha > timezone.localdate():
            self.add_error("fecha_movimiento", "No se puede registrar un movimiento con fecha futura.")

        if cantidad is not None and cantidad <= 0:
            self.add_error("cantidad", "La cantidad debe ser mayor que cero.")

        if almacen and recurso and recurso.team_id != almacen.team_id:
            self.add_error("recurso", "El recurso no pertenece a la misma empresa que el almacén.")

        if almacen and unidad_obra and unidad_obra.obra_id != almacen.obra_id:
            self.add_error("unidad_obra", "La vivienda/unidad debe pertenecer a la misma obra del almacén.")

        if almacen and partida and partida.team_id != almacen.team_id:
            self.add_error("partida", "La partida no pertenece a la misma empresa que el almacén.")

        if almacen and empleado and empleado.team_id != almacen.team_id:
            self.add_error("empleado", "El empleado no pertenece a la misma empresa que el almacén.")

        if recurso and not unidad:
            cleaned["unidad"] = recurso.unidad or ""

        if tipo in ("SALIDA", "ROTURA") and recurso and cantidad is not None:
            stock_actual = recurso.stock if recurso.stock is not None else Decimal("0")
            if stock_actual < cantidad:
                self.add_error(
                    "cantidad",
                    f"Stock insuficiente. Stock actual: {stock_actual}. Movimiento solicitado: {cantidad}.",
                )

        return cleaned
