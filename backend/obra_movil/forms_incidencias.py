from django import forms
from django.utils import timezone

from obra_movil.models import IncidenciaObraMovil
from planificacion_obra.models import (
    EmpleadoObra,
    ObraPlanificacion,
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


def _posted(data, key):
    if not data:
        return None
    value = data.get(key)
    return value if value not in ("", None) else None


class IncidenciaMovilFiltroForm(forms.Form):
    estado = forms.ChoiceField(
        label="Estado",
        required=False,
        choices=[("", "Todas")] + list(IncidenciaObraMovil.Estado.choices),
    )
    prioridad = forms.ChoiceField(
        label="Prioridad",
        required=False,
        choices=[("", "Todas")] + list(IncidenciaObraMovil.Prioridad.choices),
    )
    q = forms.CharField(
        label="Buscar",
        required=False,
        max_length=120,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select form-select-lg")
            else:
                field.widget.attrs.setdefault("class", "form-control form-control-lg")

        self.fields["q"].widget.attrs.setdefault("placeholder", "Título, descripción, obra, vivienda...")


class IncidenciaObraMovilForm(forms.ModelForm):
    class Meta:
        model = IncidenciaObraMovil
        fields = [
            "obra",
            "unidad_obra",
            "tarea_obra",
            "empleado",
            "tipo",
            "prioridad",
            "estado",
            "fecha",
            "titulo",
            "descripcion",
            "resolucion",
        ]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}),
            "descripcion": forms.Textarea(attrs={"rows": 4}),
            "resolucion": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request

        data = self.data if self.is_bound else None

        obras = _apply_mobile_team_scope(
            ObraPlanificacion.objects.select_related("team"), request
        )
        unidades = _apply_mobile_team_scope(
            UnidadObra.objects.select_related("team", "obra"), request
        )
        tareas = _apply_mobile_team_scope(
            TareaObra.objects.select_related("team", "obra", "unidad_obra", "capitulo", "partida"), request
        )
        empleados = _apply_mobile_team_scope(
            EmpleadoObra.objects.select_related("team").filter(situacion=EmpleadoObra.Situacion.ACTIVO), request
        )

        obra_id = _posted(data, "obra")
        unidad_id = _posted(data, "unidad_obra")

        if not self.is_bound and self.instance and self.instance.pk:
            obra_id = self.instance.obra_id
            unidad_id = self.instance.unidad_obra_id

        if obra_id:
            unidades = unidades.filter(obra_id=obra_id)
            tareas = tareas.filter(obra_id=obra_id)

        if unidad_id:
            tareas = tareas.filter(unidad_obra_id=unidad_id)

        self.fields["obra"].queryset = obras.order_by("legacy_cod_obra", "nombre", "id")
        self.fields["unidad_obra"].queryset = unidades.order_by("obra__legacy_cod_obra", "edificio", "vivienda", "nivel", "id")
        self.fields["tarea_obra"].queryset = tareas.order_by("obra__legacy_cod_obra", "unidad_obra__edificio", "unidad_obra__vivienda", "legacy_capitulo", "legacy_partida", "-id")
        self.fields["empleado"].queryset = empleados.order_by("nombre", "id")

        self.fields["obra"].label_from_instance = lambda obj: f"{obj.legacy_cod_obra} · {obj.nombre}"
        self.fields["unidad_obra"].label_from_instance = self._label_unidad
        self.fields["tarea_obra"].label_from_instance = self._label_tarea
        self.fields["empleado"].label_from_instance = lambda obj: obj.nombre or str(obj)

        self.fields["fecha"].initial = self.fields["fecha"].initial or timezone.localdate()

        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select form-select-lg")
            else:
                field.widget.attrs.setdefault("class", "form-control form-control-lg")

        self.fields["titulo"].widget.attrs.setdefault("placeholder", "Resumen breve de la incidencia")
        self.fields["descripcion"].widget.attrs.setdefault("placeholder", "Describe qué ocurre, dónde y qué hace falta revisar")
        self.fields["resolucion"].widget.attrs.setdefault("placeholder", "Opcional. Cómo se resolvió o qué queda pendiente")

    def _label_unidad(self, obj):
        return " · ".join(str(x) for x in [
            getattr(obj.obra, "nombre", None),
            obj.edificio,
            obj.vivienda,
            obj.nivel,
        ] if x not in ("", None))

    def _label_tarea(self, obj):
        return " · ".join(str(x) for x in [
            getattr(obj.obra, "nombre", None),
            getattr(getattr(obj, "unidad_obra", None), "edificio", None),
            getattr(getattr(obj, "unidad_obra", None), "vivienda", None),
            getattr(getattr(obj, "capitulo", None), "codigo", None),
            getattr(getattr(obj, "partida", None), "codigo", None),
            obj.programacion,
        ] if x not in ("", None))

    def clean(self):
        cleaned = super().clean()

        obra = cleaned.get("obra")
        unidad = cleaned.get("unidad_obra")
        tarea = cleaned.get("tarea_obra")
        empleado = cleaned.get("empleado")
        fecha = cleaned.get("fecha")
        estado = cleaned.get("estado")
        resolucion = (cleaned.get("resolucion") or "").strip()

        if fecha and fecha > timezone.localdate():
            self.add_error("fecha", "No se puede crear una incidencia con fecha futura.")

        if unidad and obra and unidad.obra_id != obra.id:
            self.add_error("unidad_obra", "La vivienda/unidad no pertenece a la obra seleccionada.")

        if tarea and obra and tarea.obra_id != obra.id:
            self.add_error("tarea_obra", "La tarea no pertenece a la obra seleccionada.")

        if tarea and unidad and tarea.unidad_obra_id and tarea.unidad_obra_id != unidad.id:
            self.add_error("tarea_obra", "La tarea no pertenece a la vivienda/unidad seleccionada.")

        if empleado and obra and empleado.team_id != obra.team_id:
            self.add_error("empleado", "El empleado no pertenece a la misma empresa que la obra.")

        if estado in [IncidenciaObraMovil.Estado.RESUELTA, IncidenciaObraMovil.Estado.CERRADA] and not resolucion:
            self.add_error("resolucion", "Indica la resolución antes de marcar como resuelta o cerrada.")

        return cleaned
