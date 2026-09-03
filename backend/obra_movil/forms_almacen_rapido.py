from decimal import Decimal

from django import forms
from django.db.models import Q
from django.utils import timezone

from planificacion_obra.models import (
    AlmacenObra,
    EmpleadoObra,
    PartidaCatalogo,
    RecursoCatalogo,
    TareaObra,
    UnidadObra,
)
from planificacion_obra.utils import get_active_team


# OBRA_MOVIL_ALMACEN_RAPIDO_FORM_V1

TIPO_RECURSO_CHOICES = [
    ("", "Todos"),
    ("MATERIAL", "Material"),
    ("MAQUINARIA", "Maquinaria"),
    ("HERRAMIENTA", "Herramienta"),
    ("EPIS", "E.P.I.S."),
]

TIPO_MOVIMIENTO_CHOICES = [
    ("SALIDA", "Salida"),
    ("ENTRADA", "Entrada"),
    ("CONTROL_STOCK", "C. Stock"),
    ("ROTURA", "Rotura"),
]

DESTINO_CHOICES = [
    ("PARTIDA", "A vivienda / partida"),
    ("PERSONA", "A persona / pendiente"),
    ("ALMACEN", "Solo almacén"),
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


def _value(data, key):
    if not data:
        return ""
    value = data.get(key)
    return "" if value is None else str(value).strip()


def _tipo_filter(qs, tipo):
    tipo = (tipo or "").strip().upper()

    if not tipo:
        return qs

    if tipo == "EPIS":
        return qs.filter(Q(tipo__icontains="E.P") | Q(tipo__icontains="EPI"))

    return qs.filter(tipo__icontains=tipo)


class AlmacenRapidoForm(forms.Form):
    tipo_recurso = forms.ChoiceField(
        label="Tipo artículo",
        required=False,
        choices=TIPO_RECURSO_CHOICES,
    )
    q_recurso = forms.CharField(
        label="Artículo",
        required=False,
        max_length=120,
    )

    almacen = forms.ModelChoiceField(
        label="Almacén",
        queryset=AlmacenObra.objects.none(),
        required=True,
    )
    recurso = forms.ModelChoiceField(
        label="Artículo seleccionado",
        queryset=RecursoCatalogo.objects.none(),
        required=True,
    )

    tipo_movimiento = forms.ChoiceField(
        label="Movimiento",
        choices=TIPO_MOVIMIENTO_CHOICES,
        widget=forms.RadioSelect,
        initial="SALIDA",
    )

    cantidad = forms.DecimalField(
        label="Cantidad",
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

    destino = forms.ChoiceField(
        label="Destino",
        choices=DESTINO_CHOICES,
        widget=forms.RadioSelect,
        initial="PARTIDA",
    )

    unidad_obra = forms.ModelChoiceField(
        label="Vivienda / unidad",
        queryset=UnidadObra.objects.none(),
        required=False,
    )
    partida = forms.ModelChoiceField(
        label="Capítulo / partida",
        queryset=PartidaCatalogo.objects.none(),
        required=False,
    )
    empleado = forms.ModelChoiceField(
        label="Persona",
        queryset=EmpleadoObra.objects.none(),
        required=False,
    )

    observaciones = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    vehiculo = forms.CharField(
        label="Vehículo / máquina",
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={
            "placeholder": "FURGONETA NUEVA, MANITOU, CITROEN...",
            "list": "alm2VehiculosGasoil",
            "autocomplete": "off",
        }),
    )
    kilometraje = forms.DecimalField(
        label="KM/HRS",
        required=False,
        min_value=Decimal("0"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            "step": "0.01",
            "placeholder": "Kilómetros u horas",
            "inputmode": "decimal",
        }),
    )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request

        data = self.data if self.is_bound else None

        tipo_recurso = _value(data, "tipo_recurso") or _value(self.initial, "tipo_recurso")
        q_recurso = _value(data, "q_recurso") or _value(self.initial, "q_recurso")
        almacen_id = _value(data, "almacen") or _value(self.initial, "almacen")
        recurso_id = _value(data, "recurso") or _value(self.initial, "recurso")
        unidad_id = _value(data, "unidad_obra") or _value(self.initial, "unidad_obra")

        almacenes = _apply_mobile_team_scope(
            AlmacenObra.objects.select_related("team", "obra"), request
        ).order_by("obra__legacy_cod_obra", "legacy_id_almacen", "nombre", "id")

        self.fields["almacen"].queryset = almacenes
        self.fields["almacen"].label_from_instance = self._label_almacen

        almacen = None
        if almacen_id:
            almacen = almacenes.filter(pk=almacen_id).first()

        recursos_base = _apply_mobile_team_scope(
            RecursoCatalogo.objects.select_related("team", "capitulo").filter(control_stock=True),
            request,
        )

        recursos_base = _tipo_filter(recursos_base, tipo_recurso)

        if recurso_id:
            recursos_qs = recursos_base.filter(pk=recurso_id)
        elif q_recurso:
            filtro = Q(nombre__icontains=q_recurso)
            if q_recurso.isdigit():
                filtro |= Q(legacy_id=int(q_recurso))
            # BUSQUEDAS_ARTICULOS_SIN_LIMITE_V1
            # El desplegable utiliza scroll: no ocultar coincidencias.
            recursos_qs = recursos_base.filter(filtro).order_by(
                "tipo",
                "nombre",
                "legacy_id",
                "id",
            )
        else:
            recursos_qs = recursos_base.none()

        self.recursos_disponibles_count = recursos_base.count() if q_recurso else 0
        self.fields["recurso"].queryset = recursos_qs
        self.fields["recurso"].label_from_instance = self._label_recurso

        self.resource_unit_map = {
            str(obj.pk): (
                str(obj.unidad or "")
                .strip()
            )
            for obj in recursos_qs
            if str(
                obj.unidad or ""
            ).strip()
        }

        if (
            not self.is_bound
            and recurso_id
        ):
            selected_resource = (
                recursos_qs
                .filter(pk=recurso_id)
                .first()
            )

            if (
                selected_resource
                and str(
                    selected_resource.unidad
                    or ""
                ).strip()
            ):
                self.initial["unidad"] = (
                    str(
                        selected_resource.unidad
                    ).strip()
                )

        unidades = _apply_mobile_team_scope(
            UnidadObra.objects.select_related("team", "obra"), request
        )
        tareas = _apply_mobile_team_scope(
            TareaObra.objects.select_related("team", "obra", "unidad_obra", "capitulo", "partida"), request
        )

        empleados = _apply_mobile_team_scope(
            EmpleadoObra.objects.select_related("team").filter(situacion=EmpleadoObra.Situacion.ACTIVO),
            request,
        )

        if almacen is not None:
            unidades = unidades.filter(obra=almacen.obra)
            tareas = tareas.filter(obra=almacen.obra)
            empleados = empleados.filter(team=almacen.team)

        if unidad_id:
            tareas = tareas.filter(unidad_obra_id=unidad_id)

        partida_ids = tareas.exclude(partida__isnull=True).values_list("partida_id", flat=True).distinct()

        self.fields["unidad_obra"].queryset = unidades.order_by("edificio", "vivienda", "nivel", "id")
        self.fields["partida"].queryset = PartidaCatalogo.objects.filter(pk__in=partida_ids).order_by("capitulo__codigo", "codigo", "id")
        self.fields["empleado"].queryset = empleados.order_by("nombre", "id")

        self.fields["unidad_obra"].label_from_instance = self._label_unidad
        self.fields["partida"].label_from_instance = self._label_partida
        self.fields["empleado"].label_from_instance = lambda obj: obj.nombre or str(obj)

        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, forms.RadioSelect):
                widget.attrs.setdefault("class", "obra-radio-list")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select form-select-lg")
            elif not isinstance(widget, forms.HiddenInput):
                widget.attrs.setdefault("class", "form-control form-control-lg")

        self.fields["q_recurso"].widget.attrs.setdefault("placeholder", "Código o texto. Ej: TORN, 383...")
        self.fields["cantidad"].widget.attrs.setdefault("step", "0.0001")
        self.fields["unidad"].widget.attrs.setdefault("placeholder", "UD, CAJAS, CUBAS, L...")
        self.fields["observaciones"].widget.attrs.setdefault("placeholder", "Nota rápida para oficina")
        # ALM GASOIL UX: asegurar variantes de litro válidas en el selector de unidad.
        unidad_field = self.fields.get("unidad")
        if unidad_field is not None and hasattr(unidad_field, "choices"):
            existing_choices = list(unidad_field.choices)
            existing_values = {str(value) for value, _label in existing_choices}
            for value, label in [
                ("LTRS", "LTRS"),
                ("LTS", "LTS"),
                ("LT", "LT"),
                ("L", "L"),
            ]:
                if value not in existing_values:
                    existing_choices.append((value, label))
                    existing_values.add(value)
            for value in sorted(
                set(
                    self.resource_unit_map
                    .values()
                )
            ):
                if value not in existing_values:
                    existing_choices.append(
                        (value, value)
                    )
                    existing_values.add(value)

            unidad_field.choices = existing_choices


    def _label_almacen(self, obj):
        return " · ".join(str(x) for x in [
            getattr(obj.obra, "legacy_cod_obra", None),
            getattr(obj.obra, "nombre", None),
            obj.nombre,
        ] if x not in ("", None))

    def _label_recurso(self, obj):
        return " · ".join(str(x) for x in [
            obj.tipo,
            obj.legacy_id,
            obj.nombre,
            obj.unidad,
            f"Stock: {obj.stock if obj.stock is not None else 0}",
        ] if x not in ("", None))

    def _label_unidad(self, obj):
        return " · ".join(str(x) for x in [
            obj.edificio,
            obj.vivienda,
            obj.nivel,
        ] if x not in ("", None))

    def _label_partida(self, obj):
        capitulo = getattr(obj, "capitulo", None)
        return " · ".join(str(x) for x in [
            getattr(capitulo, "codigo", None),
            getattr(capitulo, "nombre", None),
            getattr(obj, "codigo", None),
            getattr(obj, "nombre", None),
        ] if x not in ("", None))

    def clean(self):
        cleaned = super().clean()

        almacen = cleaned.get("almacen")
        recurso = cleaned.get("recurso")
        tipo_movimiento = cleaned.get("tipo_movimiento")
        cantidad = cleaned.get("cantidad")
        unidad = (cleaned.get("unidad") or "").strip()
        fecha = cleaned.get("fecha_movimiento")
        destino = cleaned.get("destino")
        unidad_obra = cleaned.get("unidad_obra")
        partida = cleaned.get("partida")
        empleado = cleaned.get("empleado")

        if fecha and fecha > timezone.localdate():
            self.add_error("fecha_movimiento", "No se puede registrar con fecha futura.")

        recurso_unidad = (
            str(
                getattr(
                    recurso,
                    "unidad",
                    "",
                )
                or ""
            )
            .strip()
            if recurso
            else ""
        )

        if recurso_unidad:
            cleaned["unidad"] = (
                recurso_unidad
            )

        if almacen and recurso and recurso.team_id != almacen.team_id:
            self.add_error("recurso", "El artículo no pertenece a la misma empresa que el almacén.")

        if cantidad is not None:
            if tipo_movimiento == "CONTROL_STOCK":
                if cantidad < 0:
                    self.add_error("cantidad", "El control de stock no puede ser negativo.")
            elif cantidad <= 0:
                self.add_error("cantidad", "La cantidad debe ser mayor que cero.")

        # ALMACEN_RAPIDO_STOCK_NEGATIVO_V1
        # SALIDA/ROTURA puede superar el stock disponible.
        # La falta de stock es una advertencia operativa, no un bloqueo.
        # El movimiento se registra y el saldo resultante puede ser negativo.

        if tipo_movimiento in ("ENTRADA", "CONTROL_STOCK"):
            cleaned["destino"] = "ALMACEN"
            cleaned["unidad_obra"] = None
            cleaned["partida"] = None
            cleaned["empleado"] = None
        elif destino == "PARTIDA":
            if not unidad_obra:
                self.add_error("unidad_obra", "Indica la vivienda/unidad.")
            if not partida:
                self.add_error("partida", "Indica capítulo/partida.")
            cleaned["empleado"] = None
        elif destino == "PERSONA":
            if not empleado:
                self.add_error("empleado", "Indica la persona que recibe el material.")
            cleaned["unidad_obra"] = None
            cleaned["partida"] = None
        else:
            self.add_error("destino", "Indica si va a partida o a persona.")

        if almacen and unidad_obra and unidad_obra.obra_id != almacen.obra_id:
            self.add_error("unidad_obra", "La vivienda/unidad no pertenece a la obra del almacén.")

        if empleado and almacen and empleado.team_id != almacen.team_id:
            self.add_error("empleado", "La persona no pertenece a la misma empresa que el almacén.")

        vehiculo = (cleaned.get("vehiculo") or "").strip()
        kilometraje = cleaned.get("kilometraje")

        is_gasoil = False
        if recurso:
            nombre_recurso = str(getattr(recurso, "nombre", "") or "").strip().upper()
            legacy_recurso = getattr(recurso, "legacy_id", None)
            is_gasoil = legacy_recurso == 167 or nombre_recurso == "GASOIL"

        if is_gasoil and tipo_movimiento == "SALIDA":
            if destino != "PERSONA":
                self.add_error("destino", "Para salida de GASOIL selecciona A persona / pendiente.")
            if not empleado:
                self.add_error("empleado", "Indica quién recarga.")
            if not vehiculo:
                self.add_error("vehiculo", "Indica el vehículo o máquina.")
            if kilometraje is None:
                self.add_error("kilometraje", "Indica KM/HRS.")

            cleaned["vehiculo"] = vehiculo
            cleaned["kilometraje"] = kilometraje
        else:
            cleaned["vehiculo"] = ""
            cleaned["kilometraje"] = None

        return cleaned


# OBRA_MOVIL_ALM_UX2B6_UNIDAD_ALMACEN_OK
# UX Obra móvil: unidad no editable libremente.
# Se presenta como desplegable con unidades existentes y se valida en backend.
_ALM_UX2B6_UNIDADES_BASE = [
    "UD", "UND", "UNIDAD", "UNIDADES",
    "M", "ML", "M2", "M3",
    "KG", "GR", "L", "LT",
    "ROLLO", "ROLLOS",
    "CAJA", "CAJAS",
    "SACO", "SACOS",
    "PAQUETE", "PAQUETES",
    "CUBAS", "CUBA",
    "PORTE", "PORTES",
    "H", "HORAS", "JORNADA", "JOR",
]

def _alm_ux2b6_norm_unidad(value):
    return str(value or "").strip().upper()

def _alm_ux2b6_unidades_choices():
    values = set(_ALM_UX2B6_UNIDADES_BASE)

    try:
        qs = (
            RecursoCatalogo.objects
            .exclude(unidad__isnull=True)
            .exclude(unidad__exact="")
            .values_list("unidad", flat=True)
            .distinct()
        )

        for value in qs[:1000]:
            unit = _alm_ux2b6_norm_unidad(value)
            if unit:
                values.add(unit)
    except Exception:
        pass

    ordered = sorted(values, key=lambda x: (len(x), x))

    return [("", "---------")] + [(v, v) for v in ordered]

_ALM_UX2B6_ORIGINAL_INIT = AlmacenRapidoForm.__init__
_ALM_UX2B6_ORIGINAL_CLEAN = AlmacenRapidoForm.clean

def _alm_ux2b6_init(self, *args, **kwargs):
    _ALM_UX2B6_ORIGINAL_INIT(self, *args, **kwargs)

    if "unidad" in self.fields:
        choices = _alm_ux2b6_unidades_choices()
        old_attrs = dict(getattr(self.fields["unidad"].widget, "attrs", {}) or {})

        old_attrs.setdefault("class", "form-select")
        old_attrs.setdefault("data-alm2-unidad-select", "1")

        self.fields["unidad"].widget = forms.Select(
            choices=choices,
            attrs=old_attrs,
        )

        self.fields["unidad"].help_text = "Selecciona una unidad existente. No escribir unidades a mano."

def _alm_ux2b6_clean(self):
    cleaned = _ALM_UX2B6_ORIGINAL_CLEAN(self)

    unidad = _alm_ux2b6_norm_unidad(cleaned.get("unidad"))

    if unidad:
        valid = {value for value, _label in _alm_ux2b6_unidades_choices() if value}

        if unidad not in valid:
            self.add_error("unidad", "Selecciona una unidad válida del listado.")

        cleaned["unidad"] = unidad

    return cleaned

AlmacenRapidoForm.__init__ = _alm_ux2b6_init
AlmacenRapidoForm.clean = _alm_ux2b6_clean


# OBRA_MOVIL_ALM_UX2E1_V2_PLANIFICACION_PARTIDA_OK
# Validación segura por wrapper: evita insertar código dentro de la clase.
_alm_ux2e1_original_clean = getattr(AlmacenRapidoForm, "clean", None)


def _alm_ux2e1_clean_partida_completa(self):
    cleaned = _alm_ux2e1_original_clean(self) if callable(_alm_ux2e1_original_clean) else {}

    tipo_movimiento = str(cleaned.get("tipo_movimiento") or "").upper()
    destino = str(cleaned.get("destino") or "").upper()
    unidad_obra = cleaned.get("unidad_obra")
    partida = cleaned.get("partida")

    if tipo_movimiento in {"SALIDA", "ROTURA"} and destino == "PARTIDA":
        if not unidad_obra:
            self.add_error("unidad_obra", "Para enviar a vivienda / partida debes seleccionar la vivienda completa.")
        if not partida:
            self.add_error("partida", "Para enviar a vivienda / partida debes seleccionar hasta la partida.")

        if unidad_obra and partida:
            try:
                from planificacion_obra.models import TareaObra

                qs_tarea = TareaObra.objects.filter(
                    unidad_obra=unidad_obra,
                    partida=partida,
                )

                recurso = cleaned.get("recurso")
                if recurso is not None and getattr(recurso, "team_id", None):
                    qs_tarea = qs_tarea.filter(team_id=recurso.team_id)

                if not qs_tarea.exists():
                    self.add_error("partida", "No existe tarea de planificación para esa vivienda y partida.")
            except Exception as exc:
                self.add_error("partida", f"No se pudo validar la tarea de planificación: {exc}")

    return cleaned


AlmacenRapidoForm.clean = _alm_ux2e1_clean_partida_completa



# OBRA_MOVIL_ALM_UX2E1_V3_POST_QUERYSETS_OK
# En POST, los selects jerárquicos llegan por campos ocultos/unidad_obra/partida.
# Hay que aceptar esos IDs antes de la validación del ModelChoiceField.
_alm_ux2e1_v3_original_init = AlmacenRapidoForm.__init__


def _alm_ux2e1_v3_init_accept_post_destino(self, *args, **kwargs):
    _alm_ux2e1_v3_original_init(self, *args, **kwargs)

    try:
        from planificacion_obra.models import TareaObra

        unidad_model = TareaObra._meta.get_field("unidad_obra").remote_field.model
        partida_model = TareaObra._meta.get_field("partida").remote_field.model

        data = getattr(self, "data", None)
        unidad_id = ""
        partida_id = ""

        if data:
            unidad_id = str(data.get("unidad_obra") or "").strip()
            partida_id = str(data.get("partida") or "").strip()

        if "unidad_obra" in self.fields:
            current_qs = getattr(self.fields["unidad_obra"], "queryset", unidad_model.objects.none())

            if unidad_id:
                self.fields["unidad_obra"].queryset = (
                    unidad_model.objects
                    .filter(pk=unidad_id)
                    | current_qs
                ).distinct()
            else:
                self.fields["unidad_obra"].queryset = current_qs

        if "partida" in self.fields:
            current_qs = getattr(self.fields["partida"], "queryset", partida_model.objects.none())

            if partida_id:
                self.fields["partida"].queryset = (
                    partida_model.objects
                    .filter(pk=partida_id)
                    | current_qs
                ).distinct()
            else:
                self.fields["partida"].queryset = current_qs

    except Exception:
        # No romper el formulario si el introspector falla.
        pass


AlmacenRapidoForm.__init__ = _alm_ux2e1_v3_init_accept_post_destino



# OBRA_MOVIL_ALM_UX2E1_V4_CLEANED_DATA_DESTINO_OK
# Reparación final: si unidad_obra/partida llegan como IDs válidos en POST,
# convertirlos a objetos aunque el queryset inicial del campo no los hubiera incluido.
_alm_ux2e1_v4_previous_clean = AlmacenRapidoForm.clean


def _alm_ux2e1_v4_clean_repair_destino(self):
    cleaned = _alm_ux2e1_v4_previous_clean(self)

    tipo_movimiento = str(cleaned.get("tipo_movimiento") or "").upper()
    destino = str(cleaned.get("destino") or "").upper()

    if tipo_movimiento not in {"SALIDA", "ROTURA"} or destino != "PARTIDA":
        return cleaned

    try:
        from planificacion_obra.models import TareaObra

        unidad_model = TareaObra._meta.get_field("unidad_obra").remote_field.model
        partida_model = TareaObra._meta.get_field("partida").remote_field.model

        data = getattr(self, "data", None)
        unidad_id = str(data.get("unidad_obra") or "").strip() if data else ""
        partida_id = str(data.get("partida") or "").strip() if data else ""

        unidad_obra = cleaned.get("unidad_obra")
        partida = cleaned.get("partida")

        if not unidad_obra and unidad_id:
            unidad_obra = unidad_model.objects.filter(pk=unidad_id).first()
            if unidad_obra:
                cleaned["unidad_obra"] = unidad_obra
                if hasattr(self, "_errors"):
                    self._errors.pop("unidad_obra", None)

        if not partida and partida_id:
            partida = partida_model.objects.filter(pk=partida_id).first()
            if partida:
                cleaned["partida"] = partida
                if hasattr(self, "_errors"):
                    self._errors.pop("partida", None)

        if not unidad_obra:
            self.add_error("unidad_obra", "Para enviar a vivienda / partida debes seleccionar la vivienda completa.")

        if not partida:
            self.add_error("partida", "Para enviar a vivienda / partida debes seleccionar hasta la partida.")

        if unidad_obra and partida:
            qs_tarea = TareaObra.objects.filter(
                unidad_obra=unidad_obra,
                partida=partida,
            )

            recurso = cleaned.get("recurso")
            if recurso is not None and getattr(recurso, "team_id", None):
                qs_tarea = qs_tarea.filter(team_id=recurso.team_id)

            if not qs_tarea.exists():
                self.add_error("partida", "No existe tarea de planificación para esa vivienda y partida.")

    except Exception as exc:
        self.add_error("partida", f"No se pudo validar la tarea de planificación: {exc}")

    return cleaned


AlmacenRapidoForm.clean = _alm_ux2e1_v4_clean_repair_destino



# OBRA_MOVIL_ALM_UX2E1_V6_STOCK_OPERATIVO_OK
def _alm_ux2e1_v6_decimal(value):
    from decimal import Decimal

    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "."))
    except Exception:
        return Decimal("0")


# OBRA_MOVIL_ALM_UX2E1_V6_STOCK_OPERATIVO_OK
def _alm_ux2e1_v6_stock_operativo_form(recurso, almacen):
    """
    Devuelve el stock del recurso en el almacén seleccionado, usando la misma fuente visual
    que el buscador de almacén rápido cuando es posible.
    """
    if not recurso or not almacen:
        return _alm_ux2e1_v6_decimal(getattr(recurso, "stock", 0))

    try:
        from obra_movil import views as ov

        fn = getattr(ov, "_alm_ux1d_lookup_stocks", None)
        if callable(fn):
            rows = fn(recurso.pk)

            if isinstance(rows, dict):
                rows = rows.get("almacenes") or rows.get("results") or []

            for row in rows or []:
                if not isinstance(row, dict):
                    continue

                row_id = str(row.get("id") or row.get("almacen_id") or "")
                if row_id == str(almacen.pk):
                    if row.get("stock_numeric") is not None:
                        return _alm_ux2e1_v6_decimal(row.get("stock_numeric"))
                    return _alm_ux2e1_v6_decimal(row.get("stock"))
    except Exception:
        pass

    try:
        from planificacion_obra.models import RecursoAlmacenMovimiento

        ultimo = (
            RecursoAlmacenMovimiento.objects
            .filter(recurso=recurso, almacen=almacen)
            .exclude(quedan__isnull=True)
            .order_by("-fecha_movimiento", "-hora_movimiento", "-created_at", "-pk")
            .first()
        )

        if ultimo is not None:
            return _alm_ux2e1_v6_decimal(ultimo.quedan)
    except Exception:
        pass

    return _alm_ux2e1_v6_decimal(getattr(recurso, "stock", 0))


# OBRA_MOVIL_ALM_UX2E1_V6_STOCK_OPERATIVO_OK
_alm_ux2e1_v6_previous_clean = AlmacenRapidoForm.clean


def _alm_ux2e1_v6_clean_stock_operativo(self):
    cleaned = _alm_ux2e1_v6_previous_clean(self)

    try:
        from django.utils import timezone

        # Si la fecha no viene en POST, usar hoy y quitar el error obligatorio.
        if not cleaned.get("fecha_movimiento"):
            cleaned["fecha_movimiento"] = timezone.localdate()
            if hasattr(self, "_errors"):
                self._errors.pop("fecha_movimiento", None)

        tipo = str(cleaned.get("tipo_movimiento") or "").upper()
        if tipo in {"SALIDA", "ROTURA"}:
            recurso = cleaned.get("recurso")
            almacen = cleaned.get("almacen")
            cantidad = _alm_ux2e1_v6_decimal(cleaned.get("cantidad"))
            stock_operativo = _alm_ux2e1_v6_stock_operativo_form(recurso, almacen)

            if recurso and almacen and cantidad > 0 and stock_operativo >= cantidad:
                # Quitar error heredado por stock global negativo si el almacén sí tiene stock.
                if hasattr(self, "_errors"):
                    self._errors.pop("cantidad", None)

                cleaned["_stock_operativo_almacen"] = stock_operativo

    except Exception:
        pass

    return cleaned


AlmacenRapidoForm.clean = _alm_ux2e1_v6_clean_stock_operativo



# OBRA_MOVIL_ALM_UX2E1_V7_STOCK_ALMACEN_REAL_OK
def _alm_ux2e1_v7_decimal(value):
    from decimal import Decimal

    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "."))
    except Exception:
        return Decimal("0")


# OBRA_MOVIL_ALM_UX2E1_V7_STOCK_ALMACEN_REAL_OK
def _alm_ux2e1_v7_stock_almacen_real(recurso, almacen):
    """
    Stock operativo real del recurso en el almacén seleccionado.
    Usa la suma de 'quedan' porque esas filas son las que alimentan el stock visual por almacén.
    """
    if not recurso or not almacen:
        return _alm_ux2e1_v7_decimal(getattr(recurso, "stock", 0))

    try:
        from django.db.models import Sum
        from planificacion_obra.models import RecursoAlmacenMovimiento

        agg = (
            RecursoAlmacenMovimiento.objects
            .filter(recurso=recurso, almacen=almacen)
            .exclude(quedan__isnull=True)
            .aggregate(total=Sum("quedan"))
        )

        total = _alm_ux2e1_v7_decimal(agg.get("total"))

        if total != 0:
            return total
    except Exception:
        pass

    return _alm_ux2e1_v7_decimal(getattr(recurso, "stock", 0))


# OBRA_MOVIL_ALM_UX2E1_V7_STOCK_ALMACEN_REAL_OK
_alm_ux2e1_v7_previous_clean = AlmacenRapidoForm.clean


def _alm_ux2e1_v7_clean_stock_almacen_real(self):
    cleaned = _alm_ux2e1_v7_previous_clean(self)

    try:
        from django.utils import timezone
        from planificacion_obra.models import RecursoCatalogo, AlmacenObra

        data = getattr(self, "data", None)

        # Fecha por defecto si no viene desde móvil/smoke.
        if not cleaned.get("fecha_movimiento"):
            cleaned["fecha_movimiento"] = timezone.localdate()
            if hasattr(self, "_errors"):
                self._errors.pop("fecha_movimiento", None)

        tipo = str(cleaned.get("tipo_movimiento") or (data.get("tipo_movimiento") if data else "") or "").upper()

        if tipo in {"SALIDA", "ROTURA"}:
            cantidad = _alm_ux2e1_v7_decimal(
                cleaned.get("cantidad") if cleaned.get("cantidad") not in (None, "") else (data.get("cantidad") if data else None)
            )

            recurso = cleaned.get("recurso")
            almacen = cleaned.get("almacen")

            if not recurso and data and data.get("recurso"):
                recurso = RecursoCatalogo.objects.filter(pk=str(data.get("recurso")).strip()).first()
                if recurso:
                    cleaned["recurso"] = recurso

            if not almacen and data and data.get("almacen"):
                almacen = AlmacenObra.objects.filter(pk=str(data.get("almacen")).strip()).first()
                if almacen:
                    cleaned["almacen"] = almacen

            stock_operativo = _alm_ux2e1_v7_stock_almacen_real(recurso, almacen)

            if recurso and almacen and cantidad > 0 and stock_operativo >= cantidad:
                cleaned["cantidad"] = cantidad
                cleaned["_stock_operativo_almacen"] = stock_operativo

                # Quitar el falso error heredado desde RecursoCatalogo.stock global.
                if hasattr(self, "_errors"):
                    self._errors.pop("cantidad", None)

    except Exception as exc:
        # No añadir error nuevo aquí; la validación original sigue actuando.
        try:
            cleaned.setdefault("_alm_ux2e1_v7_error", str(exc))
        except Exception:
            pass

    return cleaned


AlmacenRapidoForm.clean = _alm_ux2e1_v7_clean_stock_almacen_real



# OBRA_MOVIL_ALM_UX2F1_PERSONAL_OBRA_ACTIVO_OK
def _alm_ux2f1_personal_obra_activo_queryset(request=None, base_qs=None):
    """
    Mismo universo funcional que Planning de Obra · Nueva asignación de personal:
    solo personal de obra administrado, activo, sin baja y vinculado a RRHH.
    Excluye contratados/recurso tipo M.O.C., horas, partidas y textos de contratista.
    """
    from planificacion_obra.models import EmpleadoObra
    from planificacion_obra.utils import get_active_team

    qs = EmpleadoObra.objects.filter(
        tipo=EmpleadoObra.Tipo.ADMINISTRADA,
        situacion=EmpleadoObra.Situacion.ACTIVO,
        fecha_baja__isnull=True,
    ).exclude(
        rrhh_empleado_id__isnull=True,
    )

    # Respetar el scope que ya había calculado el formulario, si existe.
    try:
        if base_qs is not None:
            team_ids = list(base_qs.values_list("team_id", flat=True).distinct())
            if team_ids:
                qs = qs.filter(team_id__in=team_ids)
    except Exception:
        pass

    user = getattr(request, "user", None)

    try:
        active_team_id = request.session.get("active_team_id") if request is not None else None
    except Exception:
        active_team_id = None

    if active_team_id not in (None, "", "all"):
        try:
            active_team = get_active_team(request)
        except Exception:
            active_team = None

        if active_team is not None:
            qs = qs.filter(team=active_team)

    elif user is not None and not getattr(user, "is_superuser", False) and hasattr(user, "teams"):
        qs = qs.filter(team__in=user.teams.all())

    return qs.order_by("nombre", "id")


_alm_ux2f1_previous_init = AlmacenRapidoForm.__init__


def _alm_ux2f1_init_personal_obra_activo(self, *args, **kwargs):
    request = kwargs.get("request")
    _alm_ux2f1_previous_init(self, *args, **kwargs)

    if request is None:
        request = getattr(self, "request", None)

    if "empleado" in self.fields:
        base_qs = getattr(self.fields["empleado"], "queryset", None)
        self.fields["empleado"].queryset = _alm_ux2f1_personal_obra_activo_queryset(
            request=request,
            base_qs=base_qs,
        )
        self.fields["empleado"].label = "Personal de obra"
        self.fields["empleado"].label_from_instance = lambda obj: obj.nombre or str(obj)
        self.fields["empleado"].help_text = "Solo personal de obra activo. Las entregas a persona quedan pendientes de imputar a partida."


AlmacenRapidoForm.__init__ = _alm_ux2f1_init_personal_obra_activo



# OBRA_MOVIL_ALM_UX2F2_EXCLUIR_PERSONAL_GENERICO_OK
# Capa final sobre el selector de PERSONA: excluir registros genéricos legacy.
_alm_ux2f2_previous_init = AlmacenRapidoForm.__init__


def _alm_ux2f2_init_excluir_personal_generico(self, *args, **kwargs):
    _alm_ux2f2_previous_init(self, *args, **kwargs)

    if "empleado" in self.fields:
        from django.db.models import Q

        qs = self.fields["empleado"].queryset

        qs = qs.exclude(
            Q(legacy_id=0) |
            Q(nombre__icontains="GENERIC") |
            Q(nombre__icontains="GENERICO") |
            Q(nombre__icontains="GENÉRICO")
        )

        self.fields["empleado"].queryset = qs.order_by("nombre", "id")
        self.fields["empleado"].label = "Personal de obra"
        self.fields["empleado"].help_text = "Solo personal de obra activo. Las entregas a persona quedan pendientes de imputar a partida."


AlmacenRapidoForm.__init__ = _alm_ux2f2_init_excluir_personal_generico

