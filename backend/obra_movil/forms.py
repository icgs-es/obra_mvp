from decimal import Decimal

from django import forms
from django.utils import timezone

from planificacion_obra.models import (
    CapituloCatalogo,
    EmpleadoObra,
    ObraPlanificacion,
    PartidaCatalogo,
    RecursoCatalogo,
    TareaObra,
    UnidadObra,
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


def _val(data, key):
    if not data:
        return None
    value = data.get(key)
    return value if value not in ("", None) else None


class ProduccionMovilFiltroForm(forms.Form):
    f_obra = forms.ModelChoiceField(
        queryset=ObraPlanificacion.objects.none(),
        required=False,
        label="Obra",
    )
    f_unidad_obra = forms.ModelChoiceField(
        queryset=UnidadObra.objects.none(),
        required=False,
        label="Vivienda / unidad",
    )
    f_capitulo = forms.ModelChoiceField(
        queryset=CapituloCatalogo.objects.none(),
        required=False,
        label="Capítulo",
    )
    f_partida = forms.ModelChoiceField(
        queryset=PartidaCatalogo.objects.none(),
        required=False,
        label="Partida",
    )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        data = self.data if self.is_bound else None

        obras = _apply_mobile_team_scope(ObraPlanificacion.objects.all(), request)
        unidades = _apply_mobile_team_scope(
            UnidadObra.objects.select_related("obra", "fase"), request
        )
        capitulos = _apply_mobile_team_scope(CapituloCatalogo.objects.all(), request)
        partidas = _apply_mobile_team_scope(
            PartidaCatalogo.objects.select_related("capitulo"), request
        )

        obra_id = _val(data, "f_obra")
        unidad_id = _val(data, "f_unidad_obra")
        capitulo_id = _val(data, "f_capitulo")

        if obra_id:
            unidades = unidades.filter(obra_id=obra_id)

        if capitulo_id:
            partidas = partidas.filter(capitulo_id=capitulo_id)

        self.fields["f_obra"].queryset = obras.order_by("legacy_cod_obra", "nombre", "id")
        self.fields["f_unidad_obra"].queryset = unidades.order_by("obra__legacy_cod_obra", "edificio", "vivienda", "id")
        self.fields["f_capitulo"].queryset = capitulos.order_by("codigo", "nombre", "id")
        self.fields["f_partida"].queryset = partidas.order_by("capitulo__codigo", "codigo", "nombre", "id")

        self.fields["f_obra"].label_from_instance = lambda obj: f"{obj.legacy_cod_obra or ''} · {obj.nombre}".strip(" ·")
        self.fields["f_unidad_obra"].label_from_instance = self._label_unidad
        self.fields["f_capitulo"].label_from_instance = lambda obj: f"{obj.codigo} · {obj.nombre}"
        self.fields["f_partida"].label_from_instance = lambda obj: f"{obj.codigo} · {obj.nombre}"

        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-select form-select-lg")

    def _label_unidad(self, obj):
        partes = [
            getattr(getattr(obj, "obra", None), "nombre", None),
            obj.edificio,
            obj.vivienda,
            obj.nivel,
        ]
        return " · ".join(str(x) for x in partes if x not in ("", None))


class ProduccionMovilForm(forms.Form):
    MODO_EMPLEADO = "EMPLEADO"
    MODO_RECURSO = "RECURSO"

    MODO_CHOICES = [
        (MODO_EMPLEADO, "Mano de obra"),
        (MODO_RECURSO, "Material / recurso"),
    ]

    tarea_obra = forms.ModelChoiceField(
        queryset=TareaObra.objects.none(),
        label="Tarea",
        required=True,
    )
    modo = forms.ChoiceField(
        choices=MODO_CHOICES,
        label="Tipo",
        widget=forms.RadioSelect,
        initial=MODO_EMPLEADO,
    )
    empleado = forms.ModelChoiceField(
        queryset=EmpleadoObra.objects.none(),
        label="Empleado",
        required=False,
    )
    recurso = forms.ModelChoiceField(
        queryset=RecursoCatalogo.objects.none(),
        label="Recurso / material",
        required=False,
    )
    fecha = forms.DateField(
        label="Fecha",
        required=True,
        widget=forms.DateInput(attrs={"type": "date"}),
        initial=timezone.localdate,
    )
    cantidad = forms.DecimalField(
        label="Cantidad / horas",
        required=True,
        min_value=Decimal("0.0001"),
        decimal_places=4,
        max_digits=12,
    )
    unidad = forms.CharField(
        label="Unidad",
        required=False,
        max_length=30,
    )
    precio_unidad = forms.DecimalField(
        label="Precio unidad",
        required=False,
        min_value=Decimal("0"),
        decimal_places=4,
        max_digits=12,
    )
    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, request=None, filters=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        filters = filters or {}

        tareas = TareaObra.objects.select_related(
            "team",
            "obra",
            "unidad_obra",
            "capitulo",
            "partida",
        ).filter(
            obra__isnull=False,
            capitulo__isnull=False,
            partida__isnull=False,
        )

        recursos = RecursoCatalogo.objects.select_related("team", "capitulo").exclude(
            tipo__in=["M.O. ADM.", "M.O. CONT.", "PER. CONT.", "PARTIDA"]
        )

        empleados = EmpleadoObra.objects.select_related("team").filter(
            tipo=EmpleadoObra.Tipo.ADMINISTRADA,
            situacion=EmpleadoObra.Situacion.ACTIVO,
        )

        tareas = _apply_mobile_team_scope(tareas, request)
        recursos = _apply_mobile_team_scope(recursos, request)
        empleados = _apply_mobile_team_scope(empleados, request)

        f_obra = _val(filters, "f_obra")
        f_unidad = _val(filters, "f_unidad_obra")
        f_capitulo = _val(filters, "f_capitulo")
        f_partida = _val(filters, "f_partida")

        has_filters = any([f_obra, f_unidad, f_capitulo, f_partida])

        if f_obra:
            tareas = tareas.filter(obra_id=f_obra)
        if f_unidad:
            tareas = tareas.filter(unidad_obra_id=f_unidad)
        if f_capitulo:
            tareas = tareas.filter(capitulo_id=f_capitulo)
        if f_partida:
            tareas = tareas.filter(partida_id=f_partida)

        tareas = tareas.order_by(
            "obra__legacy_cod_obra",
            "unidad_obra__edificio",
            "unidad_obra__vivienda",
            "legacy_planta",
            "legacy_capitulo",
            "legacy_partida",
            "-id",
        )

        # OBRA_MOVIL_FORM_TEAM_SCOPE_V2
        # OBRA_MOVIL_TAREA_LIMIT_V1
        # Sin filtros, no cargamos miles de tareas en móvil: mostramos las últimas 250.
        self.tareas_limitadas = not has_filters
        if not has_filters:
            tareas = tareas.order_by("-id")[:250]

        self.fields["tarea_obra"].queryset = tareas
        self.fields["recurso"].queryset = recursos.order_by("tipo", "nombre", "id")
        self.fields["empleado"].queryset = empleados.order_by("nombre", "id")

        self.fields["tarea_obra"].label_from_instance = self._label_tarea
        self.fields["recurso"].label_from_instance = self._label_recurso
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
        self.fields["precio_unidad"].widget.attrs.setdefault("step", "0.0001")
        self.fields["unidad"].widget.attrs.setdefault("placeholder", "HRS, UD, M2, ML...")
        self.fields["observaciones"].widget.attrs.setdefault("placeholder", "Nota opcional desde obra")

    def _label_tarea(self, obj):
        partes = [
            getattr(getattr(obj, "obra", None), "nombre", None),
            getattr(getattr(obj, "unidad_obra", None), "edificio", None),
            getattr(getattr(obj, "unidad_obra", None), "vivienda", None),
            getattr(obj, "legacy_planta", None),
            getattr(getattr(obj, "capitulo", None), "codigo", None),
            getattr(getattr(obj, "partida", None), "codigo", None),
            getattr(obj, "programacion", None),
        ]
        return " · ".join(str(x) for x in partes if x not in ("", None))

    def _label_recurso(self, obj):
        partes = [
            obj.tipo,
            obj.legacy_id,
            obj.nombre,
            obj.unidad,
        ]
        return " · ".join(str(x) for x in partes if x not in ("", None))

    def clean(self):
        cleaned = super().clean()

        tarea = cleaned.get("tarea_obra")
        modo = cleaned.get("modo")
        empleado = cleaned.get("empleado")
        recurso = cleaned.get("recurso")
        fecha = cleaned.get("fecha")
        cantidad = cleaned.get("cantidad")
        unidad = (cleaned.get("unidad") or "").strip()
        precio = cleaned.get("precio_unidad")

        if fecha and fecha > timezone.localdate():
            self.add_error("fecha", "No se puede registrar producción real con fecha futura.")

        if cantidad is not None and cantidad <= 0:
            self.add_error("cantidad", "La cantidad debe ser mayor que cero.")

        if modo == self.MODO_EMPLEADO:
            if not empleado:
                self.add_error("empleado", "Selecciona un empleado.")
            if recurso:
                self.add_error("recurso", "En mano de obra no debe seleccionarse recurso.")
            if tarea and empleado and empleado.team_id != tarea.team_id:
                self.add_error("empleado", "El empleado no pertenece a la misma empresa que la tarea.")
            cleaned["unidad"] = unidad or "HRS"
            if empleado and precio is None:
                cleaned["precio_unidad"] = empleado.precio_hora or Decimal("0")

        elif modo == self.MODO_RECURSO:
            if not recurso:
                self.add_error("recurso", "Selecciona un recurso o material.")
            if empleado:
                self.add_error("empleado", "En material/recurso no debe seleccionarse empleado.")
            if tarea and recurso and recurso.team_id != tarea.team_id:
                self.add_error("recurso", "El recurso no pertenece a la misma empresa que la tarea.")
            if recurso:
                cleaned["unidad"] = unidad or recurso.unidad or ""
                if precio is None:
                    cleaned["precio_unidad"] = (
                        recurso.precio_unidad_uso
                        or recurso.ultimo_precio_unidad
                        or Decimal("0")
                    )

        return cleaned
