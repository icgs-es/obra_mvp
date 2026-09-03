from datetime import date, time

from django import forms
from django.utils import timezone

from rrhh.models import Empleado

from .models import (
    AsignacionObra,
    CapituloCatalogo,
    FaseObra,
    ObraPlanificacion,
    PartidaCatalogo,
    TareaObra,
    UnidadObra,
)




# ---------------------------------------------------------------------
# FIX PLANIFICACION OBRA:
# Nivel físico de UnidadObra NO participa en planificación.
# Planta operativa = TareaObra.legacy_planta.
# ---------------------------------------------------------------------




# ---------------------------------------------------------------------
# FIX REAL PLANIFICACION OBRA
# Nivel NO participa.
# Planta = TareaObra.legacy_planta.
# Filtros por modelos reales del formulario.
# ---------------------------------------------------------------------




# ---------------------------------------------------------------------
# FIX FINAL:
# Asegurar queryset de empleado RRHH en AsignacionObraForm.
# No afecta CORE OBRAS.
# ---------------------------------------------------------------------




# ---------------------------------------------------------------------
# FIX CLEAN FINAL:
# Evita error cuando obra es campo auxiliar y viene None en clean antiguo.
# Validación operativa basada en tarea_obra.obra y planta_trabajo.
# ---------------------------------------------------------------------




# ---------------------------------------------------------------------
# FIX FINAL CHOICES:
# - Nivel fuera.
# - vivienda/unidad_obra aceptan la unidad seleccionada.
# - estado usa choices reales del modelo/formulario.
# - Planta sigue siendo TareaObra.legacy_planta.
# ---------------------------------------------------------------------

# ---------------------------------------------------------------------
# AsignacionObraForm limpio
# Flujo operativo:
# Empleado -> Obra -> Edificio/Fase -> Vivienda -> Planta -> Capítulo
# -> Partida -> Tarea existente -> Guardar asignación
#
# Importante:
# - UnidadObra.nivel queda fuera del flujo operativo.
# - Planta se toma de TareaObra.legacy_planta.
# - AsignacionObra no tiene campo obra directo; la obra se valida contra tarea_obra.obra.
# ---------------------------------------------------------------------
class AsignacionObraForm(forms.ModelForm):
    obra = forms.ModelChoiceField(
        queryset=None,
        required=True,
        label="Obra",
    )

    fase = forms.ChoiceField(
        required=False,
        label="Edificio/Fase",
        choices=[("", "---------")],
    )

    vivienda = forms.ModelChoiceField(
        queryset=None,
        required=False,
        label="Vivienda",
    )

    planta_trabajo = forms.ChoiceField(
        required=True,
        label="Planta",
        choices=[("", "---------")],
    )

    class Meta:
        from django.apps import apps

        model = apps.get_model("planificacion_obra", "AsignacionObra")

        fields = [
            "empleado",
            "obra",
            "fase",
            "vivienda",
            "planta_trabajo",
            "tarea_obra",
            "unidad_obra",
            "capitulo",
            "partida",
            "fecha_inicio",
            "hora_inicio",
            "fecha_fin",
            "hora_fin",
            "estado",
            "observaciones",
        ]

        widgets = {
            "fecha_inicio": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "fecha_fin": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "hora_inicio": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
            "hora_fin": forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
            "observaciones": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        from django.apps import apps
        from django.db.models import Q
        from django.utils import timezone

        self.request_user = kwargs.pop("request_user", None)

        super().__init__(*args, **kwargs)

        self.fields.pop("nivel", None)

        ObraPlanificacion = apps.get_model("planificacion_obra", "ObraPlanificacion")
        UnidadObra = apps.get_model("planificacion_obra", "UnidadObra")
        TareaObra = apps.get_model("planificacion_obra", "TareaObra")
        CapituloCatalogo = apps.get_model("planificacion_obra", "CapituloCatalogo")
        PartidaCatalogo = apps.get_model("planificacion_obra", "PartidaCatalogo")
        Empleado = apps.get_model("rrhh", "Empleado")

        data = self.data if self.is_bound else None

        def posted(name):
            if not data:
                return None
            value = data.get(name)
            return value if value not in ("", None) else None

        def model_fields(model):
            return {f.name for f in model._meta.fields}

        def filtered_by_user_team(qs):
            user = self.request_user

            if not user or not hasattr(user, "teams"):
                return qs

            try:
                teams = user.teams.all()
            except Exception:
                return qs

            if not teams.exists():
                return qs

            if "team" in model_fields(qs.model):
                return qs.filter(team__in=teams)

            return qs

        def unit_text_field_names():
            names = []

            for f in UnidadObra._meta.fields:
                n = f.name.lower()

                if "nivel" in n:
                    continue

                if "fase" in n or "edificio" in n or "bloque" in n:
                    names.append(f.name)

            return names

        def clean_fase_label(value):
            import re

            if value is None:
                return ""

            text = str(value).strip()

            m = re.search(r"(EDIFICIO\s+[A-Z0-9]+)", text, flags=re.I)
            if m:
                return m.group(1).upper()

            m = re.search(r"(FASE\s+[A-Z0-9]+)", text, flags=re.I)
            if m:
                return m.group(1).upper()

            if "·" in text:
                return text.split("·")[-1].strip()

            return text

        def value_as_text(obj, names):
            for name in names:
                value = getattr(obj, name, None)
                if value not in ("", None):
                    return clean_fase_label(value)
            return clean_fase_label(obj)

        def as_pk(value):
            return getattr(value, "pk", value)

        instance = self.instance if getattr(self.instance, "pk", None) else None
        tarea_inst = getattr(instance, "tarea_obra", None) if instance else None
        unidad_inst = None

        if instance:
            unidad_inst = getattr(instance, "unidad_obra", None)

        if not unidad_inst and tarea_inst:
            unidad_inst = getattr(tarea_inst, "unidad_obra", None)

        obra_id = as_pk(
            posted("obra")
            or self.initial.get("obra")
            or getattr(tarea_inst, "obra_id", None)
            or getattr(unidad_inst, "obra_id", None)
        )

        fase = posted("fase") or self.initial.get("fase")

        unidad_id = as_pk(
            posted("unidad_obra")
            or posted("vivienda")
            or self.initial.get("unidad_obra")
            or self.initial.get("vivienda")
            or getattr(unidad_inst, "pk", None)
        )

        planta = (
            posted("planta_trabajo")
            or self.initial.get("planta_trabajo")
            or getattr(tarea_inst, "legacy_planta", None)
        )

        capitulo_id = as_pk(
            posted("capitulo")
            or self.initial.get("capitulo")
            or getattr(instance, "capitulo_id", None)
            or getattr(tarea_inst, "capitulo_id", None)
        )

        partida_id = as_pk(
            posted("partida")
            or self.initial.get("partida")
            or getattr(instance, "partida_id", None)
            or getattr(tarea_inst, "partida_id", None)
        )

        tarea_id = as_pk(
            posted("tarea_obra")
            or self.initial.get("tarea_obra")
            or getattr(instance, "tarea_obra_id", None)
        )

        # Defaults fecha/hora solo para nueva asignación.
        # En edición se respetan los valores existentes del instance.
        if not self.is_bound and not getattr(self.instance, "pk", None):
            today = timezone.localdate()

            self.fields["fecha_inicio"].initial = today
            self.fields["fecha_fin"].initial = today
            self.fields["hora_inicio"].initial = "08:00"
            self.fields["hora_fin"].initial = "14:00" if today.weekday() == 4 else "18:00"

        self.fields["fecha_inicio"].input_formats = ["%Y-%m-%d"]
        self.fields["fecha_fin"].input_formats = ["%Y-%m-%d"]
        self.fields["hora_inicio"].input_formats = ["%H:%M"]
        self.fields["hora_fin"].input_formats = ["%H:%M"]

        # Empleados RRHH aptos para planificación de obra.
        # Regla: solo empleados vinculados a EmpleadoObra legacy.
        EmpleadoObra = apps.get_model("planificacion_obra", "EmpleadoObra")

        empleados_obra = (
            EmpleadoObra.objects
            .exclude(rrhh_empleado_id__isnull=True)
            .filter(
                tipo=EmpleadoObra.Tipo.ADMINISTRADA,
                situacion__iexact="ACTIVO",
                fecha_baja__isnull=True,
            )
        )

        if self.request_user and getattr(self.request_user, "is_authenticated", False):
            user_team_ids = list(self.request_user.teams.values_list("id", flat=True))
            if user_team_ids:
                empleados_obra = empleados_obra.filter(team_id__in=user_team_ids)

        empleado_ids_validos = empleados_obra.values_list("rrhh_empleado_id", flat=True)

        empleados = Empleado.objects.filter(id__in=empleado_ids_validos)

        # ASIGNACION_NO_FILTRAR_FLAGS_RRHH_V3
        # En planificación de obra manda EmpleadoObra:
        # tipo ADMINISTRADA + situación ACTIVO + fecha_baja NULL + rrhh_empleado vinculado.
        # No filtramos por Empleado.activo ni Empleado.es_planificable_obra porque esos flags
        # pueden no estar sincronizados en altas recientes.

        # Si se edita una asignación antigua con empleado fuera de regla,
        # se conserva visible para no romper el formulario existente.
        if getattr(self.instance, "empleado_id", None):
            empleados = Empleado.objects.filter(
                Q(id__in=empleados.values_list("id", flat=True)) |
                Q(id=self.instance.empleado_id)
            )

        # ASIGNACION_EMPLEADOOBRA_ACTIVO_SOURCE_V2
        # En planificación manda EmpleadoObra ADMINISTRADA + ACTIVO + sin fecha baja.
        # No se excluye por flags RRHH activo/es_planificable_obra porque algunos empleados nuevos
        # ya están operativos en EmpleadoObra pero esos flags no están sincronizados.
        empleado_obra_label_map = {}
        for eo in empleados_obra.order_by("rrhh_empleado_id", "-id"):
            if eo.rrhh_empleado_id and int(eo.rrhh_empleado_id) not in empleado_obra_label_map:
                empleado_obra_label_map[int(eo.rrhh_empleado_id)] = eo.nombre or ""

        def _label_empleado_desde_empleado_obra(emp):
            return (
                empleado_obra_label_map.get(int(emp.pk))
                or getattr(emp, "nombre_completo", None)
                or getattr(emp, "nombre", None)
                or str(emp)
            )

        self.fields["empleado"].queryset = empleados.order_by("nombre_completo", "id")
        self.fields["empleado"].label_from_instance = _label_empleado_desde_empleado_obra

        # Obras
        obras = filtered_by_user_team(ObraPlanificacion.objects.all())
        self.fields["obra"].queryset = obras.order_by("codigo", "id")

        # Unidades / viviendas
        unidades = filtered_by_user_team(UnidadObra.objects.all())

        if obra_id:
            unidades = unidades.filter(obra_id=obra_id)

        fase_fields = unit_text_field_names()

        if not fase and unidad_inst:
            fase = value_as_text(unidad_inst, fase_fields)

        if not self.is_bound:
            initial_values = {
                "obra": obra_id,
                "fase": fase,
                "vivienda": unidad_id,
                "unidad_obra": unidad_id,
                "planta_trabajo": planta,
                "capitulo": capitulo_id,
                "partida": partida_id,
                "tarea_obra": tarea_id,
            }

            for field_name, field_value in initial_values.items():
                if field_value not in ("", None) and field_name in self.fields:
                    self.initial[field_name] = field_value
                    self.fields[field_name].initial = field_value

        fases = []
        seen = set()

        for unidad in unidades.order_by("id"):
            text = value_as_text(unidad, fase_fields)
            if text and text not in seen:
                seen.add(text)
                fases.append((text, text))

        if fase and fase not in seen:
            fases.append((fase, fase))

        self.fields["fase"].choices = [("", "---------")] + fases

        if fase and fase_fields:
            # Fase/Edificio es un texto visible de agrupación.
            # No se filtra con ORM sobre FK porque puede provocar:
            # Field 'id' expected a number but got '2 · ALTOVELOO · EDIFICIO C'
            unidad_ids = []

            for unidad in unidades:
                if value_as_text(unidad, fase_fields) == fase:
                    unidad_ids.append(unidad.pk)

            unidades = UnidadObra.objects.filter(pk__in=unidad_ids)

        if unidad_id:
            ids = list(unidades.values_list("pk", flat=True))
            try:
                ids.append(int(unidad_id))
            except Exception:
                pass
            unidades = UnidadObra.objects.filter(pk__in=set(ids))

        unidades = unidades.distinct().order_by("id")

        self.fields["vivienda"].queryset = unidades
        self.fields["unidad_obra"].queryset = unidades
        self.fields["unidad_obra"].required = False

        # Tareas operativas
        tareas = filtered_by_user_team(TareaObra.objects.all())

        if obra_id:
            tareas = tareas.filter(obra_id=obra_id)

        if unidad_id:
            tareas = tareas.filter(unidad_obra_id=unidad_id)

        # Planta SIEMPRE desde TareaObra.legacy_planta
        plantas_qs = tareas

        plantas = list(
            plantas_qs.exclude(legacy_planta__isnull=True)
            .exclude(legacy_planta="")
            .order_by("legacy_planta")
            .values_list("legacy_planta", flat=True)
            .distinct()
        )

        planta_choices = [("", "---------")] + [(p, p) for p in plantas if p]

        if planta and planta not in [x[0] for x in planta_choices]:
            planta_choices.append((planta, planta))

        self.fields["planta_trabajo"].choices = planta_choices

        if planta:
            tareas = tareas.filter(legacy_planta=planta)

        if capitulo_id:
            tareas = tareas.filter(capitulo_id=capitulo_id)

        if partida_id:
            tareas = tareas.filter(partida_id=partida_id)

        if tarea_id:
            ids = list(tareas.values_list("pk", flat=True))
            try:
                ids.append(int(tarea_id))
            except Exception:
                pass
            tareas = TareaObra.objects.filter(pk__in=set(ids))

        tareas = tareas.distinct()

        self.fields["tarea_obra"].queryset = tareas

        capitulo_ids = tareas.exclude(capitulo_id__isnull=True).values_list("capitulo_id", flat=True)
        partida_ids = tareas.exclude(partida_id__isnull=True).values_list("partida_id", flat=True)

        capitulos = CapituloCatalogo.objects.filter(pk__in=capitulo_ids).distinct()

        if capitulo_id:
            ids = list(capitulos.values_list("pk", flat=True))
            try:
                ids.append(int(capitulo_id))
            except Exception:
                pass
            capitulos = CapituloCatalogo.objects.filter(pk__in=set(ids))

        partidas = PartidaCatalogo.objects.filter(pk__in=partida_ids).distinct()

        if partida_id:
            ids = list(partidas.values_list("pk", flat=True))
            try:
                ids.append(int(partida_id))
            except Exception:
                pass
            partidas = PartidaCatalogo.objects.filter(pk__in=set(ids))

        self.fields["capitulo"].queryset = capitulos
        self.fields["partida"].queryset = partidas

        self.fields["fase"].required = False
        self.fields["vivienda"].required = False

    def clean(self):
        from django import forms as django_forms

        cleaned = super().clean()

        tarea = cleaned.get("tarea_obra")
        obra = cleaned.get("obra")
        vivienda = cleaned.get("vivienda")
        unidad_obra = cleaned.get("unidad_obra") or vivienda
        capitulo = cleaned.get("capitulo")
        partida = cleaned.get("partida")
        planta = cleaned.get("planta_trabajo")

        if not tarea:
            return cleaned

        if obra and getattr(tarea, "obra_id", None) and tarea.obra_id != obra.id:
            raise django_forms.ValidationError("La tarea seleccionada no pertenece a la obra indicada.")

        if unidad_obra and getattr(tarea, "unidad_obra_id", None):
            unidad_id = unidad_obra.id if hasattr(unidad_obra, "id") else int(unidad_obra)

            if tarea.unidad_obra_id != unidad_id:
                raise django_forms.ValidationError("La tarea seleccionada no pertenece a la vivienda indicada.")

            cleaned["unidad_obra"] = tarea.unidad_obra

        if capitulo and getattr(tarea, "capitulo_id", None) and tarea.capitulo_id != capitulo.id:
            raise django_forms.ValidationError("La tarea seleccionada no pertenece al capítulo indicado.")

        if partida and getattr(tarea, "partida_id", None) and tarea.partida_id != partida.id:
            raise django_forms.ValidationError("La tarea seleccionada no pertenece a la partida indicada.")

        if planta and getattr(tarea, "legacy_planta", None) and tarea.legacy_planta != planta:
            raise django_forms.ValidationError("La tarea seleccionada no pertenece a la planta indicada.")

        return cleaned



# ---------------------------------------------------------------------
# Guardia final: Nivel no participa en asignación de personal.
# Orden operativo: Obra -> Edificio/Fase -> Vivienda -> Planta.
# ---------------------------------------------------------------------
_NoNivelGuardAsignacionObraForm = AsignacionObraForm

class AsignacionObraForm(_NoNivelGuardAsignacionObraForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Campo prohibido en el flujo operativo.
        self.fields.pop("nivel", None)

        if "planta_trabajo" in self.fields:
            self.fields["planta_trabajo"].label = "Planta"


# ==========================================================
# Optimización rendimiento formulario nueva asignación
# ----------------------------------------------------------
# En alta nueva no se deben renderizar miles de opciones.
# Los campos dependientes se cargan mediante endpoint JS:
# Obra -> Edificio/Fase -> Vivienda -> Planta -> Capítulo -> Partida -> Tarea.
# En edición y POST se conserva el comportamiento completo para validar datos.
# ==========================================================

_FastNewAsignacionObraForm = AsignacionObraForm

class AsignacionObraForm(_FastNewAsignacionObraForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        instance = getattr(self, "instance", None)
        is_existing = bool(getattr(instance, "pk", None))

        # Solo optimizar GET de nueva asignación.
        # No tocar POST ni edición, porque necesitan querysets hidratados.
        if self.is_bound or is_existing:
            return

        for field_name in ["vivienda", "unidad_obra", "capitulo", "partida", "tarea_obra"]:
            field = self.fields.get(field_name)
            qs = getattr(field, "queryset", None)
            if qs is not None:
                field.queryset = qs.none()

        if "fase" in self.fields:
            self.fields["fase"].choices = [("", "---------")]

        if "planta_trabajo" in self.fields:
            self.fields["planta_trabajo"].choices = [("", "---------")]

# === TAREA_MANUAL_PORTAL_V1 ===
from django import forms as _tm_forms
from .models import (
    ObraPlanificacion as _TMObraPlanificacion,
    UnidadObra as _TMUnidadObra,
    CapituloCatalogo as _TMCapituloCatalogo,
    PartidaCatalogo as _TMPartidaCatalogo,
    TareaObra as _TMTareaObra,
)
from .utils import get_active_team as _tm_get_active_team


def _tm_scope_queryset(qs, request):
    if request is None:
        return qs

    active_team = _tm_get_active_team(request)
    if active_team is not None:
        return qs.filter(team=active_team)

    user = getattr(request, "user", None)
    if user is not None and not getattr(user, "is_superuser", False) and hasattr(user, "teams"):
        return qs.filter(team__in=user.teams.all())

    return qs


class TareaObraManualForm(_tm_forms.ModelForm):
    programacion = _tm_forms.CharField(
        label="Nombre / descripción corta",
        max_length=80,
        required=True,
        help_text="Texto breve para identificar la tarea manual.",
    )

    class Meta:
        model = _TMTareaObra
        fields = [
            "obra",
            "unidad_obra",
            "capitulo",
            "partida",
            "programacion",
            "legacy_planta",
            "legacy_orden",
            "inicio_tarea",
            "fin_tarea",
            "dias",
            "horas",
            "porcentaje_completado",
            "unidad",
            "cantidad",
            "precio_unidad",
            "importe_tarea",
            "personas_a_utilizar",
            "con_incidencias",
            "observaciones",
        ]
        labels = {
            "obra": "Obra",
            "unidad_obra": "Unidad / vivienda",
            "capitulo": "Capítulo",
            "partida": "Partida",
            "legacy_planta": "Planta / nivel operativo",
            "legacy_orden": "Orden",
            "inicio_tarea": "Inicio planificado",
            "fin_tarea": "Fin planificado",
            "dias": "Días previstos",
            "horas": "Horas previstas",
            "porcentaje_completado": "% completado",
            "unidad": "Unidad",
            "cantidad": "Cantidad",
            "precio_unidad": "Precio unidad",
            "importe_tarea": "Importe previsto",
            "personas_a_utilizar": "Personas previstas",
            "con_incidencias": "Con incidencias",
            "observaciones": "Observaciones",
        }
        widgets = {
            "inicio_tarea": _tm_forms.DateInput(attrs={"type": "date"}),
            "fin_tarea": _tm_forms.DateInput(attrs={"type": "date"}),
            "observaciones": _tm_forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, request=None, obra=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.obra_locked = obra

        obra_qs = _tm_scope_queryset(
            _TMObraPlanificacion.objects.select_related("team").all(),
            request,
        ).order_by("legacy_cod_obra", "nombre")

        selected_obra = obra

        if obra is not None:
            obra_qs = obra_qs.filter(pk=obra.pk)
            self.fields["obra"].initial = obra.pk
            self.fields["obra"].widget = _tm_forms.HiddenInput()
        else:
            obra_id = None
            if self.data:
                obra_id = self.data.get("obra")
            elif self.initial:
                obra_id = self.initial.get("obra")

            if obra_id:
                try:
                    selected_obra = obra_qs.get(pk=obra_id)
                except Exception:
                    selected_obra = None

        self.fields["obra"].queryset = obra_qs
        self.fields["obra"].required = True

        if selected_obra is not None:
            unidad_qs = _TMUnidadObra.objects.filter(
                team=selected_obra.team,
                obra=selected_obra,
            ).select_related("fase").order_by("edificio", "vivienda", "nivel")

            capitulo_qs = _TMCapituloCatalogo.objects.filter(
                team=selected_obra.team,
            ).order_by("orden", "codigo")

            partida_qs = _TMPartidaCatalogo.objects.filter(
                team=selected_obra.team,
            ).select_related("capitulo").order_by("capitulo__codigo", "codigo")
        else:
            unidad_qs = _tm_scope_queryset(
                _TMUnidadObra.objects.select_related("obra", "fase").all(),
                request,
            ).order_by("obra__legacy_cod_obra", "edificio", "vivienda", "nivel")

            capitulo_qs = _tm_scope_queryset(
                _TMCapituloCatalogo.objects.all(),
                request,
            ).order_by("orden", "codigo")

            partida_qs = _tm_scope_queryset(
                _TMPartidaCatalogo.objects.select_related("capitulo").all(),
                request,
            ).order_by("capitulo__codigo", "codigo")

        self.fields["unidad_obra"].queryset = unidad_qs
        self.fields["unidad_obra"].required = False
        self.fields["capitulo"].queryset = capitulo_qs
        self.fields["capitulo"].required = False
        self.fields["partida"].queryset = partida_qs
        self.fields["partida"].required = True

        self.fields["porcentaje_completado"].initial = self.fields["porcentaje_completado"].initial or 0

        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, _tm_forms.HiddenInput):
                continue
            if isinstance(widget, _tm_forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (_tm_forms.Select, _tm_forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()

        obra = self.obra_locked or cleaned.get("obra")
        unidad = cleaned.get("unidad_obra")
        capitulo = cleaned.get("capitulo")
        partida = cleaned.get("partida")
        inicio = cleaned.get("inicio_tarea")
        fin = cleaned.get("fin_tarea")
        pct = cleaned.get("porcentaje_completado")

        if self.obra_locked is not None:
            cleaned["obra"] = self.obra_locked
            obra = self.obra_locked

        if unidad and obra and unidad.obra_id != obra.id:
            self.add_error("unidad_obra", "La unidad seleccionada no pertenece a la obra.")

        if partida:
            if capitulo and partida.capitulo_id != capitulo.id:
                self.add_error("partida", "La partida no pertenece al capítulo seleccionado.")
            elif not capitulo:
                cleaned["capitulo"] = partida.capitulo

        if inicio and fin and fin < inicio:
            self.add_error("fin_tarea", "La fecha fin no puede ser anterior a la fecha de inicio.")

        if pct is not None and (pct < 0 or pct > 100):
            self.add_error("porcentaje_completado", "El porcentaje debe estar entre 0 y 100.")

        return cleaned


# === TAREA_MANUAL_SIMPLE_V2 ===
class TareaObraSimpleForm(_tm_forms.ModelForm):
    class Meta:
        model = _TMTareaObra
        fields = [
            "obra",
            "unidad_obra",
            "legacy_planta",
            "capitulo",
            "partida",
            "inicio_tarea",
            "fin_tarea",
            "dias",
            "observaciones",
        ]
        labels = {
            "obra": "Obra",
            "unidad_obra": "Vivienda / unidad",
            "legacy_planta": "Planta",
            "capitulo": "Capítulo",
            "partida": "Partida",
            "inicio_tarea": "Fecha inicio",
            "fin_tarea": "Fecha fin",
            "dias": "Días",
            "observaciones": "Observaciones",
        }
        widgets = {
            "inicio_tarea": _tm_forms.DateInput(attrs={"type": "date"}),
            "fin_tarea": _tm_forms.DateInput(attrs={"type": "date"}),
            "observaciones": _tm_forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, request=None, obra=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.obra_locked = obra

        obra_qs = _tm_scope_queryset(
            _TMObraPlanificacion.objects.select_related("team").all(),
            request,
        ).order_by("legacy_cod_obra", "nombre")

        selected_obra = obra

        if obra is not None:
            obra_qs = obra_qs.filter(pk=obra.pk)
            self.fields["obra"].initial = obra.pk
            self.fields["obra"].widget = _tm_forms.HiddenInput()
        else:
            obra_id = self.data.get("obra") if self.data else self.initial.get("obra")
            if obra_id:
                selected_obra = obra_qs.filter(pk=obra_id).first()

        self.fields["obra"].queryset = obra_qs
        self.fields["obra"].required = True

        if selected_obra is not None:
            unidad_qs = _TMUnidadObra.objects.filter(
                team=selected_obra.team,
                obra=selected_obra,
            ).select_related("fase").order_by("edificio", "vivienda", "nivel")

            capitulo_qs = _TMCapituloCatalogo.objects.filter(
                team=selected_obra.team,
            ).order_by("orden", "codigo")

            partida_qs = _TMPartidaCatalogo.objects.filter(
                team=selected_obra.team,
            ).select_related("capitulo").order_by("capitulo__codigo", "codigo")

            plantas = list(
                _TMTareaObra.objects.filter(
                    team=selected_obra.team,
                    obra=selected_obra,
                )
                .exclude(legacy_planta="")
                .values_list("legacy_planta", flat=True)
                .distinct()
                .order_by("legacy_planta")
            )
        else:
            unidad_qs = _tm_scope_queryset(
                _TMUnidadObra.objects.select_related("obra", "fase").all(),
                request,
            ).order_by("obra__legacy_cod_obra", "edificio", "vivienda", "nivel")

            capitulo_qs = _tm_scope_queryset(
                _TMCapituloCatalogo.objects.all(),
                request,
            ).order_by("orden", "codigo")

            partida_qs = _tm_scope_queryset(
                _TMPartidaCatalogo.objects.select_related("capitulo").all(),
                request,
            ).order_by("capitulo__codigo", "codigo")

            plantas = list(
                _tm_scope_queryset(_TMTareaObra.objects.all(), request)
                .exclude(legacy_planta="")
                .values_list("legacy_planta", flat=True)
                .distinct()
                .order_by("legacy_planta")
            )

        self.fields["unidad_obra"].queryset = unidad_qs
        self.fields["unidad_obra"].required = True

        # Planta real de planning: TareaObra.legacy_planta.
        # No se autocompleta desde UnidadObra.nivel.
        planta_choices = [("", "---------")] + [(p, p) for p in plantas]
        self.fields["legacy_planta"].widget = _tm_forms.Select(choices=planta_choices)
        self.fields["legacy_planta"].required = True

        self.fields["capitulo"].queryset = capitulo_qs
        self.fields["capitulo"].required = True

        self.fields["partida"].queryset = partida_qs
        self.fields["partida"].required = True

        self.fields["inicio_tarea"].required = False
        self.fields["fin_tarea"].required = False
        self.fields["dias"].required = False
        self.fields["dias"].widget.attrs["readonly"] = "readonly"

        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, _tm_forms.HiddenInput):
                continue
            if isinstance(widget, (_tm_forms.Select, _tm_forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")

        # Marcador para JS: cada option de partida lleva su capitulo_id.
        for option in self.fields["partida"].queryset:
            pass

    def clean(self):
        cleaned = super().clean()

        obra = self.obra_locked or cleaned.get("obra")
        unidad = cleaned.get("unidad_obra")
        capitulo = cleaned.get("capitulo")
        partida = cleaned.get("partida")
        planta = (cleaned.get("legacy_planta") or "").strip()
        inicio = cleaned.get("inicio_tarea")
        fin = cleaned.get("fin_tarea")

        if self.obra_locked is not None:
            cleaned["obra"] = self.obra_locked
            obra = self.obra_locked

        if not unidad:
            self.add_error("unidad_obra", "Selecciona vivienda/unidad.")

        if unidad and obra and unidad.obra_id != obra.id:
            self.add_error("unidad_obra", "La vivienda/unidad no pertenece a esta obra.")

        if not planta:
            self.add_error("legacy_planta", "Selecciona la planta de planificación.")

        if partida and capitulo and partida.capitulo_id != capitulo.id:
            self.add_error("partida", "La partida no pertenece al capítulo seleccionado.")

        # DUPLICADO_TAREA_FUNCIONAL_V1
        if obra and unidad and planta and capitulo and partida:
            dup_qs = _TMTareaObra.objects.filter(
                team=obra.team,
                obra=obra,
                unidad_obra=unidad,
                legacy_planta=planta,
                capitulo=capitulo,
                partida=partida,
            )
            if getattr(self.instance, "pk", None):
                dup_qs = dup_qs.exclude(pk=self.instance.pk)
            if dup_qs.exists():
                self.add_error(
                    None,
                    "Ya existe una tarea para esta misma vivienda, planta, capítulo y partida.",
                )

        if inicio and fin:
            if fin < inicio:
                self.add_error("fin_tarea", "La fecha fin no puede ser anterior a la fecha inicio.")
            else:
                cleaned["dias"] = (fin - inicio).days + 1
        elif not inicio and not fin:
            cleaned["dias"] = None

        return cleaned

# === TAREA_RECURSOS_MANUALES_V1 ===
from decimal import Decimal as _tr_Decimal
from .models import (
    TareaRecursoPrevisto as _TRTareaRecursoPrevisto,
    TareaRecursoReal as _TRTareaRecursoReal,
    RecursoCatalogo as _TRRecursoCatalogo,
    EmpleadoObra as _TREmpleadoObra,
)


def _tr_money(value):
    return value if value is not None else _tr_Decimal("0")


class TareaRecursoPrevistoManualForm(_tm_forms.ModelForm):
    class Meta:
        model = _TRTareaRecursoPrevisto
        fields = [
            "recurso",
            "unidad",
            "cantidad",
            "precio_unidad",
            "costo_recurso",
            "fecha_estimada_entrega",
            "control_suministros",
        ]
        labels = {
            "recurso": "Recurso",
            "unidad": "Unidad",
            "cantidad": "Cantidad",
            "precio_unidad": "Precio unidad",
            "costo_recurso": "Coste previsto",
            "fecha_estimada_entrega": "Fecha estimada entrega",
            "control_suministros": "Control suministros",
        }
        widgets = {
            "fecha_estimada_entrega": _tm_forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, tarea=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tarea = tarea

        qs = _TRRecursoCatalogo.objects.none()
        if tarea is not None:
            qs = _TRRecursoCatalogo.objects.filter(team=tarea.team).order_by("tipo", "nombre")

        self.fields["recurso"].queryset = qs
        self.fields["recurso"].required = True
        self.fields["unidad"].required = False
        self.fields["cantidad"].required = True
        self.fields["precio_unidad"].required = False
        self.fields["costo_recurso"].required = False

        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, _tm_forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (_tm_forms.Select, _tm_forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()
        recurso = cleaned.get("recurso")
        cantidad = cleaned.get("cantidad")
        precio = cleaned.get("precio_unidad")
        coste = cleaned.get("costo_recurso")
        unidad = (cleaned.get("unidad") or "").strip()

        if recurso:
            if not unidad:
                cleaned["unidad"] = recurso.unidad or ""
            if precio is None:
                precio = recurso.precio_unidad_uso or recurso.ultimo_precio_unidad
                cleaned["precio_unidad"] = precio

        if cantidad is not None and cantidad < 0:
            self.add_error("cantidad", "La cantidad no puede ser negativa.")

        if precio is not None and precio < 0:
            self.add_error("precio_unidad", "El precio no puede ser negativo.")

        if coste is None and cantidad is not None and precio is not None:
            cleaned["costo_recurso"] = cantidad * precio

        return cleaned


class TareaRecursoRealManualForm(_tm_forms.ModelForm):
    class Meta:
        model = _TRTareaRecursoReal
        fields = [
            "recurso",
            "empleado",
            "unidad",
            "cantidad",
            "precio_unidad",
            "horas_reales",
            "inicio_recurso_real",
            "fin_recurso_real",
            "costo_recurso_real",
            "observaciones",
        ]
        labels = {
            "recurso": "Recurso",
            "empleado": "Empleado",
            "unidad": "Unidad",
            "cantidad": "Cantidad",
            "precio_unidad": "Precio unidad",
            "horas_reales": "Horas",
            "inicio_recurso_real": "Fecha inicio",
            "fin_recurso_real": "Fecha fin",
            "costo_recurso_real": "Coste real",
            "observaciones": "Observaciones",
        }
        widgets = {
            "inicio_recurso_real": _tm_forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "fin_recurso_real": _tm_forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "observaciones": _tm_forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, tarea=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tarea = tarea

        recursos_qs = _TRRecursoCatalogo.objects.none()
        empleados_qs = _TREmpleadoObra.objects.none()

        if tarea is not None:
            recursos_qs = (
                _TRRecursoCatalogo.objects
                .filter(team=tarea.team)
                .exclude(tipo__in=["M.O. ADM.", "M.O. CONT.", "PER. CONT.", "PARTIDA"])
                .order_by("tipo", "nombre")
            )
            empleados_qs = _TREmpleadoObra.objects.filter(
                team=tarea.team,
                tipo__in=[
                    _TREmpleadoObra.Tipo.ADMINISTRADA,
                    _TREmpleadoObra.Tipo.CONTRATADO,
                ],
                situacion=_TREmpleadoObra.Situacion.ACTIVO,
            ).order_by("tipo", "nombre")

        self.fields["recurso"].queryset = recursos_qs
        self.fields["empleado"].queryset = empleados_qs

        self.fields["recurso"].required = False
        self.fields["empleado"].required = False
        self.fields["unidad"].required = False
        self.fields["cantidad"].required = False
        self.fields["precio_unidad"].required = False
        # PLANIFICACION_RECURSO_REAL_FORM_FECHAS_CALCULO_FIX
        self.fields["inicio_recurso_real"].input_formats = ["%Y-%m-%d"]
        self.fields["fin_recurso_real"].input_formats = ["%Y-%m-%d"]

        if self.instance and getattr(self.instance, "pk", None):
            inicio = getattr(self.instance, "inicio_recurso_real", None)
            fin = getattr(self.instance, "fin_recurso_real", None)
            if inicio:
                self.initial["inicio_recurso_real"] = inicio.isoformat()
            if fin:
                self.initial["fin_recurso_real"] = fin.isoformat()

        for _name in ["cantidad", "horas_reales", "precio_unidad", "costo_recurso_real"]:
            if _name in self.fields:
                self.fields[_name].widget.attrs.setdefault("step", "0.0001")

        # PLANIFICACION_RECURSO_REAL_CANTIDAD_EQ_HORAS_FIX
        self.fields["horas_reales"].widget = _tm_forms.HiddenInput()
        self.fields["horas_reales"].required = False
        self.fields["horas_reales"].help_text = ""
        self.fields["costo_recurso_real"].required = False

        # PLANIFICACION_RECURSO_REAL_UNIDAD_SELECT_UX1B
        unidades_set = set(["HRS", "UD"])
        if tarea is not None:
            for value in (
                _TRRecursoCatalogo.objects
                .filter(team=tarea.team)
                .exclude(unidad__isnull=True)
                .values_list("unidad", flat=True)
                .distinct()
            ):
                value = str(value or "").strip()
                if value:
                    unidades_set.add(value)

        unidades = sorted(unidades_set, key=lambda x: (x.upper() != "HRS", x.upper()))
        unidad_choices = [("", "---------")] + [(u, u) for u in unidades]
        self.fields["unidad"].widget = _tm_forms.Select(choices=unidad_choices)
        self.fields["unidad"].choices = unidad_choices
        self.fields["unidad"].required = False

        for name, field in self.fields.items():
            widget = field.widget
            if isinstance(widget, (_tm_forms.Select, _tm_forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()

        recurso = cleaned.get("recurso")
        empleado = cleaned.get("empleado")
        unidad = (cleaned.get("unidad") or "").strip()
        cantidad = cleaned.get("cantidad")
        precio = cleaned.get("precio_unidad")
        # Cantidad equivale a horas reales en recursos reales manuales.
        horas = cleaned.get("cantidad")
        cleaned["horas_reales"] = horas
        coste = cleaned.get("costo_recurso_real")
        inicio = cleaned.get("inicio_recurso_real")
        fin = cleaned.get("fin_recurso_real")

        # EMPLEADO_REAL_MOADM_MOCONT_ACTIVO_GUARD_V2
        if empleado:
            tipos_validos = [
                _TREmpleadoObra.Tipo.ADMINISTRADA,
                _TREmpleadoObra.Tipo.CONTRATADO,
            ]
            if empleado.tipo not in tipos_validos or empleado.situacion != _TREmpleadoObra.Situacion.ACTIVO:
                self.add_error("empleado", "Solo se pueden seleccionar empleados activos administrados o contratados.")

            # Precio hora 0 permitido: el coste quedará a 0 hasta actualizar la ficha.

        if not recurso and not empleado:
            raise _tm_forms.ValidationError("Selecciona un recurso o un empleado.")

        if recurso and empleado:
            raise _tm_forms.ValidationError("Selecciona solo recurso o solo empleado, no ambos.")

        # RECURSO_REAL_NO_MO_LEGACY_GUARD_V2
        if recurso and recurso.tipo in ["M.O. ADM.", "M.O. CONT.", "PER. CONT.", "PARTIDA"]:
            self.add_error("recurso", "La mano de obra debe cargarse desde Empleado, no desde Recurso.")

        if recurso:
            if not unidad:
                cleaned["unidad"] = recurso.unidad or ""
            if precio is None:
                precio = recurso.precio_unidad_uso or recurso.ultimo_precio_unidad
                cleaned["precio_unidad"] = precio

        if empleado:
            cleaned["unidad"] = unidad or "HRS"
            if precio is None:
                precio = empleado.precio_hora
                cleaned["precio_unidad"] = precio

        if cantidad is not None and cantidad < 0:
            self.add_error("cantidad", "La cantidad no puede ser negativa.")

        if horas is not None and horas < 0:
            self.add_error("horas_reales", "Las horas no pueden ser negativas.")

        if precio is not None and precio < 0:
            self.add_error("precio_unidad", "El precio no puede ser negativo.")

        if inicio and fin and fin < inicio:
            self.add_error("fin_recurso_real", "La fecha fin no puede ser anterior a la fecha inicio.")

        # PLANIFICACION_RECURSO_REAL_COSTE_AUTO_UX1D
        # En esta pantalla el coste real debe seguir cantidad/horas × precio.
        # Si el navegador manda 0,00 por defecto, también recalculamos.
        if precio is not None:
            nuevo_coste = None

            if empleado and horas is not None and (coste is None or coste == 0):
                nuevo_coste = horas * precio
            elif cantidad is not None and (coste is None or coste == 0):
                nuevo_coste = cantidad * precio

            if nuevo_coste is not None:
                cleaned["costo_recurso_real"] = nuevo_coste.quantize(_tr_Decimal("0.0001"))

        return cleaned

# === REALIZADO_LEGACY_EDIT_FORM_V1 ===
from decimal import Decimal as _RealizadoDecimal
from django import forms as _realizado_forms
from .models import (
    TareaRecursoReal as _RealizadoTareaRecursoReal,
    EmpleadoObra as _RealizadoEmpleadoObra,
)


class RealizadoLegacyEditForm(_realizado_forms.ModelForm):
    class Meta:
        model = _RealizadoTareaRecursoReal
        fields = [
            "empleado",
            "unidad",
            "cantidad",
            "horas_reales",
            "precio_unidad",
            "inicio_recurso_real",
            "fin_recurso_real",
            "costo_recurso_real",
            "observaciones",
        ]
        labels = {
            "empleado": "Empleado",
            "unidad": "Unidad",
            "cantidad": "Cantidad interna",
            "horas_reales": "Horas",
            "precio_unidad": "Precio hora",
            "inicio_recurso_real": "Fecha inicio",
            "fin_recurso_real": "Fecha fin",
            "costo_recurso_real": "Importe real",
            "observaciones": "Observaciones",
        }
        widgets = {
            "inicio_recurso_real": _realizado_forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "fin_recurso_real": _realizado_forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "observaciones": _realizado_forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        }

    def __init__(self, *args, team=None, **kwargs):
        super().__init__(*args, **kwargs)

        empleados_qs = _RealizadoEmpleadoObra.objects.filter(
            tipo=_RealizadoEmpleadoObra.Tipo.ADMINISTRADA,
            situacion=_RealizadoEmpleadoObra.Situacion.ACTIVO,
            fecha_baja__isnull=True,
        )

        if team is not None:
            empleados_qs = empleados_qs.filter(team=team)

        self.fields["empleado"].queryset = empleados_qs.order_by("nombre", "id")
        self.fields["empleado"].label_from_instance = lambda obj: obj.nombre or str(obj)

        for name in ["unidad", "cantidad", "horas_reales", "precio_unidad", "costo_recurso_real"]:
            self.fields[name].widget.attrs.setdefault("class", "form-control")

        self.fields["empleado"].widget.attrs.setdefault("class", "form-select")
        self.fields["unidad"].widget.attrs.setdefault("placeholder", "HRS")
        self.fields["cantidad"].widget.attrs.setdefault("step", "0.01")
        self.fields["horas_reales"].widget.attrs.setdefault("step", "0.01")
        self.fields["precio_unidad"].widget.attrs.setdefault("step", "0.01")
        self.fields["costo_recurso_real"].widget.attrs.setdefault("step", "0.01")

        self.fields["unidad"].required = False
        self.fields["cantidad"].required = False
        self.fields["horas_reales"].required = False
        self.fields["precio_unidad"].required = False
        self.fields["costo_recurso_real"].required = False
        self.fields["fin_recurso_real"].required = False
        self.fields["observaciones"].required = False

    def clean(self):
        cleaned = super().clean()

        empleado = cleaned.get("empleado")
        unidad = cleaned.get("unidad")
        cantidad = cleaned.get("cantidad")
        horas_reales = cleaned.get("horas_reales")
        precio = cleaned.get("precio_unidad")
        coste = cleaned.get("costo_recurso_real")
        inicio = cleaned.get("inicio_recurso_real")
        fin = cleaned.get("fin_recurso_real")

        if fin and inicio and fin < inicio:
            self.add_error("fin_recurso_real", "La fecha fin no puede ser anterior a la fecha inicio.")

        if empleado:
            cleaned["unidad"] = unidad or "HRS"

            if precio is None:
                precio = empleado.precio_hora or _RealizadoDecimal("0")
                cleaned["precio_unidad"] = precio

        horas = horas_reales if horas_reales is not None else cantidad

        if horas is not None:
            cleaned["cantidad"] = horas
            cleaned["horas_reales"] = horas

        if coste is None and horas is not None and precio is not None:
            cleaned["costo_recurso_real"] = horas * precio

        return cleaned

# === REALIZADO_LEGACY_EDIT_FORM_V2 ===
from decimal import Decimal as _RLDecimal
from django import forms as _rl_forms
from .models import (
    TareaRecursoReal as _RLTareaRecursoReal,
    EmpleadoObra as _RLEmpleadoObra,
)


def _rl_decimal(value):
    try:
        return _RLDecimal(str(value or 0))
    except Exception:
        return _RLDecimal("0")


def _rl_effective_hours(instance):
    """
    Horas fieles al listado:
    - En históricos Access no editados, preferimos campo horas si existe.
    - En registros ya ajustados desde Portal, preferimos horas_reales/cantidad.
    """
    if not instance:
        return _RLDecimal("0")

    raw = instance.raw_data or {}
    if not isinstance(raw, dict):
        raw = {}

    portal_editado = bool(raw.get("portal_editado"))

    if portal_editado:
        candidates = [
            getattr(instance, "horas_reales", None),
            getattr(instance, "cantidad", None),
            getattr(instance, "horas", None),
        ]
    else:
        # REALIZADO_HORAS_ACCESS_PRIORITY_V3
        # En históricos Access no editados, el listado usa la hora efectiva visible.
        # Prioridad correcta: horas si tiene valor, si no cantidad, si no horas_reales.
        candidates = [
            getattr(instance, "horas", None),
            getattr(instance, "cantidad", None),
            getattr(instance, "horas_reales", None),
        ]

    for value in candidates:
        dec = _rl_decimal(value)
        if dec != 0:
            return dec

    return _RLDecimal("0")


class RealizadoLegacyEditForm(_rl_forms.ModelForm):
    class Meta:
        model = _RLTareaRecursoReal
        fields = [
            "empleado",
            "unidad",
            "cantidad",
            "horas_reales",
            "precio_unidad",
            "inicio_recurso_real",
            "fin_recurso_real",
            "costo_recurso_real",
            "observaciones",
        ]
        labels = {
            "empleado": "Empleado",
            "unidad": "Unidad",
            "cantidad": "Cantidad interna",
            "horas_reales": "Horas",
            "precio_unidad": "Precio hora",
            "inicio_recurso_real": "Fecha inicio",
            "fin_recurso_real": "Fecha fin",
            "costo_recurso_real": "Importe real",
            "observaciones": "Observaciones",
        }
        widgets = {
            "inicio_recurso_real": _rl_forms.DateInput(
                attrs={"type": "date", "class": "form-control"},
                format="%Y-%m-%d",
            ),
            "fin_recurso_real": _rl_forms.DateInput(
                attrs={"type": "date", "class": "form-control"},
                format="%Y-%m-%d",
            ),
            "observaciones": _rl_forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        }

    def __init__(self, *args, team=None, **kwargs):
        super().__init__(*args, **kwargs)

        empleados_qs = _RLEmpleadoObra.objects.filter(
            tipo=_RLEmpleadoObra.Tipo.ADMINISTRADA,
            situacion=_RLEmpleadoObra.Situacion.ACTIVO,
            fecha_baja__isnull=True,
        )

        if team is not None:
            empleados_qs = empleados_qs.filter(team=team)

        self.fields["empleado"].queryset = empleados_qs.order_by("nombre", "id")
        self.fields["empleado"].label_from_instance = lambda obj: obj.nombre or str(obj)

        self.fields["inicio_recurso_real"].input_formats = ["%Y-%m-%d"]
        self.fields["fin_recurso_real"].input_formats = ["%Y-%m-%d"]

        for name in ["unidad", "cantidad", "horas_reales", "precio_unidad", "costo_recurso_real"]:
            self.fields[name].widget.attrs.setdefault("class", "form-control")

        self.fields["empleado"].widget.attrs.setdefault("class", "form-select")
        self.fields["unidad"].widget.attrs.setdefault("placeholder", "HRS")
        self.fields["cantidad"].widget.attrs.setdefault("step", "0.01")
        self.fields["horas_reales"].widget.attrs.setdefault("step", "0.01")
        self.fields["precio_unidad"].widget.attrs.setdefault("step", "0.01")
        self.fields["costo_recurso_real"].widget.attrs.setdefault("step", "0.01")

        self.fields["unidad"].required = False
        self.fields["cantidad"].required = False
        self.fields["horas_reales"].required = False
        self.fields["precio_unidad"].required = False
        self.fields["costo_recurso_real"].required = False
        self.fields["fin_recurso_real"].required = False
        self.fields["observaciones"].required = False

        instance = getattr(self, "instance", None)
        if instance and getattr(instance, "pk", None) and not self.is_bound:
            horas = _rl_effective_hours(instance)

            inicio = getattr(instance, "inicio_recurso_real", None)
            fin = getattr(instance, "fin_recurso_real", None) or inicio

            precio = _rl_decimal(getattr(instance, "precio_unidad", None))
            if precio == 0 and getattr(instance, "empleado", None):
                precio = _rl_decimal(getattr(instance.empleado, "precio_hora", None))

            importe = horas * precio

            initial_values = {
                "cantidad": horas,
                "horas_reales": horas,
                "precio_unidad": precio,
                "costo_recurso_real": importe,
            }

            if inicio:
                initial_values["inicio_recurso_real"] = inicio.isoformat()

            if fin:
                initial_values["fin_recurso_real"] = fin.isoformat()

            for key, value in initial_values.items():
                self.initial[key] = value
                self.fields[key].initial = value

    def clean(self):
        cleaned = super().clean()

        empleado = cleaned.get("empleado")
        unidad = cleaned.get("unidad")
        cantidad = cleaned.get("cantidad")
        horas_reales = cleaned.get("horas_reales")
        precio = cleaned.get("precio_unidad")
        inicio = cleaned.get("inicio_recurso_real")
        fin = cleaned.get("fin_recurso_real")

        if inicio and not fin:
            cleaned["fin_recurso_real"] = inicio
            fin = inicio

        if fin and inicio and fin < inicio:
            self.add_error("fin_recurso_real", "La fecha fin no puede ser anterior a la fecha inicio.")

        if empleado:
            cleaned["unidad"] = unidad or "HRS"

            if precio is None:
                precio = empleado.precio_hora or _RLDecimal("0")
                cleaned["precio_unidad"] = precio

        horas = horas_reales if horas_reales is not None else cantidad

        if horas is not None:
            cleaned["cantidad"] = horas
            cleaned["horas_reales"] = horas

        if horas is not None and precio is not None:
            cleaned["costo_recurso_real"] = horas * precio

        return cleaned



# ============================================================
# ASIGNACION_AVANCE_ACUMULADO_FORM_V1_1
# ============================================================

_AsignacionAvanceAcumuladoBase = AsignacionObraForm


class AsignacionObraForm(_AsignacionAvanceAcumuladoBase):
    porcentaje_completado = forms.DecimalField(
        required=True,
        min_value=0,
        max_value=100,
        max_digits=6,
        decimal_places=2,
        label="% completado actual",
        help_text=(
            "Porcentaje acumulado actual de la tarea. "
            "Sustituye al anterior y no puede disminuir."
        ),
        widget=forms.NumberInput(
            attrs={
                "min": "0",
                "max": "100",
                "step": "0.01",
                "inputmode": "decimal",
                "required": "required",
            }
        ),
    )

    cantidad_ejecutada = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        label="Cantidad ejecutada",
        widget=forms.NumberInput(
            attrs={
                "min": "0",
                "step": "0.01",
                "inputmode": "decimal",
            }
        ),
    )

    class Meta(_AsignacionAvanceAcumuladoBase.Meta):
        fields = tuple(
            _AsignacionAvanceAcumuladoBase.Meta.fields
        ) + (
            "porcentaje_completado",
            "cantidad_ejecutada",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # El avance pertenece siempre a una tarea concreta.
        self.fields["tarea_obra"].required = True
        self.fields["tarea_obra"].label = "Tarea"

        tarea = None

        if getattr(
            self.instance,
            "tarea_obra_id",
            None,
        ):
            tarea = self.instance.tarea_obra

        if not tarea and self.is_bound:
            tarea_id = self.data.get("tarea_obra")

            if str(tarea_id or "").isdigit():
                from django.apps import apps

                TareaObra = apps.get_model(
                    "planificacion_obra",
                    "TareaObra",
                )

                tarea = (
                    TareaObra.objects
                    .filter(pk=int(tarea_id))
                    .first()
                )

        if not self.is_bound:
            porcentaje = (
                getattr(
                    tarea,
                    "porcentaje_completado",
                    None,
                )
                if tarea
                else None
            )

            self.fields[
                "porcentaje_completado"
            ].initial = (
                porcentaje
                if porcentaje is not None
                else 0
            )

        self.unidad_ejecutada_actual = ""

        if tarea:
            self.unidad_ejecutada_actual = (
                getattr(tarea, "unidad", "")
                or getattr(
                    getattr(tarea, "partida", None),
                    "unidad",
                    "",
                )
                or ""
            )

    def clean(self):
        from decimal import Decimal

        cleaned = super().clean()

        tarea = cleaned.get("tarea_obra")
        porcentaje = cleaned.get(
            "porcentaje_completado"
        )

        if not tarea:
            self.add_error(
                "tarea_obra",
                (
                    "Selecciona la tarea concreta para "
                    "registrar correctamente su avance."
                ),
            )
            return cleaned

        actual = (
            tarea.porcentaje_completado
            if tarea.porcentaje_completado
            is not None
            else Decimal("0.00")
        )

        if porcentaje is not None:
            nuevo = Decimal(str(porcentaje))

            if nuevo < actual:
                self.add_error(
                    "porcentaje_completado",
                    (
                        "Esta tarea ya está completada "
                        f"al {actual} %. El porcentaje "
                        "no puede disminuir."
                    ),
                )

        return cleaned


# ============================================================
# ASIGNACION_UNIDAD_PRODUCCION_MANUAL_FORM_V1
# Actualmente la unidad se selecciona manualmente.
# En una fase posterior se heredará de la partida.
# ============================================================

_AsignacionUnidadProduccionManualBase = AsignacionObraForm


class AsignacionObraForm(
    _AsignacionUnidadProduccionManualBase
):
    unidad_ejecutada = forms.ChoiceField(
        required=False,
        label="Unidad de producción",
        choices=[
            ("", "---------"),
            ("M", "Metros lineales (mts)"),
            ("M2", "Metros cuadrados (m²)"),
            ("M3", "Metros cúbicos (m³)"),
        ],
    )

    class Meta(
        _AsignacionUnidadProduccionManualBase.Meta
    ):
        fields = tuple(
            _AsignacionUnidadProduccionManualBase
            .Meta.fields
        ) + (
            "unidad_ejecutada",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if (
            not self.is_bound
            and getattr(self.instance, "pk", None)
        ):
            self.fields[
                "unidad_ejecutada"
            ].initial = (
                self.instance.unidad_ejecutada
                or ""
            )

    def clean(self):
        cleaned = super().clean()

        cantidad = cleaned.get(
            "cantidad_ejecutada"
        )

        unidad = (
            cleaned.get("unidad_ejecutada")
            or ""
        ).strip()

        if cantidad is not None and not unidad:
            self.add_error(
                "unidad_ejecutada",
                (
                    "Selecciona metros lineales, "
                    "metros cuadrados o metros cúbicos."
                ),
            )

        if cantidad is None:
            cleaned["unidad_ejecutada"] = ""

        return cleaned


# === UNIDAD_OBRA_PLANTAS_FORM_V1 ===
import json as _uop_json

from django import forms as _uop_forms

from .models import (
    UnidadObraPlanta as _UnidadObraPlanta,
)


_uop_original_init = (
    TareaObraSimpleForm.__init__
)

_uop_original_clean = (
    TareaObraSimpleForm.clean
)


def _uop_selected_unit_id(form):
    value = None

    if form.is_bound:
        value = form.data.get(
            form.add_prefix(
                "unidad_obra"
            )
        )

    if not value:
        value = form.initial.get(
            "unidad_obra"
        )

    if hasattr(value, "pk"):
        value = value.pk

    if not value:
        instance = getattr(
            form,
            "instance",
            None,
        )

        if instance is not None:
            value = getattr(
                instance,
                "unidad_obra_id",
                None,
            )

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _uop_historical_unchanged(
    form,
    unidad,
    planta,
):
    instance = getattr(
        form,
        "instance",
        None,
    )

    return bool(
        instance is not None
        and getattr(
            instance,
            "pk",
            None,
        )
        and instance.unidad_obra_id
            == unidad.pk
        and _UnidadObraPlanta
            .normalizar_nombre(
                instance.legacy_planta
            )
            == _UnidadObraPlanta
            .normalizar_nombre(
                planta
            )
    )


def _uop_init(
    self,
    *args,
    request=None,
    obra=None,
    **kwargs,
):
    _uop_original_init(
        self,
        *args,
        request=request,
        obra=obra,
        **kwargs,
    )

    self.fields[
        "unidad_obra"
    ].required = True

    unidad_ids = list(
        self.fields[
            "unidad_obra"
        ]
        .queryset
        .values_list(
            "pk",
            flat=True,
        )
    )

    plantas_por_unidad = {
        str(unidad_id): []
        for unidad_id in unidad_ids
    }

    rows = (
        _UnidadObraPlanta.objects
        .filter(
            unidad_obra_id__in=(
                unidad_ids
            ),
            activa=True,
        )
        .order_by(
            "unidad_obra_id",
            "orden",
            "nombre",
        )
        .values_list(
            "unidad_obra_id",
            "nombre",
        )
    )

    for unidad_id, nombre in rows:
        plantas_por_unidad.setdefault(
            str(unidad_id),
            [],
        ).append(nombre)

    instance = getattr(
        self,
        "instance",
        None,
    )

    if (
        instance is not None
        and getattr(
            instance,
            "pk",
            None,
        )
        and instance.unidad_obra_id
        and str(
            instance.legacy_planta
            or ""
        ).strip()
    ):
        key = str(
            instance.unidad_obra_id
        )

        current = (
            _UnidadObraPlanta
            .normalizar_nombre(
                instance.legacy_planta
            )
        )

        values = (
            plantas_por_unidad
            .setdefault(
                key,
                [],
            )
        )

        if current not in values:
            values.append(current)

    selected_unit_id = (
        _uop_selected_unit_id(
            self
        )
    )

    selected_values = (
        plantas_por_unidad.get(
            str(selected_unit_id),
            [],
        )
        if selected_unit_id
        else []
    )

    old_field = self.fields[
        "legacy_planta"
    ]

    widget_attrs = dict(
        getattr(
            old_field.widget,
            "attrs",
            {},
        )
    )

    widget_attrs["class"] = (
        "form-select"
    )

    self.fields[
        "legacy_planta"
    ] = _uop_forms.ChoiceField(
        label="Planta",
        required=True,
        choices=[
            ("", "---------"),
            *[
                (value, value)
                for value
                in selected_values
            ],
        ],
        help_text=(
            "Solo se muestran las plantas "
            "configuradas para la vivienda."
        ),
        widget=_uop_forms.Select(
            attrs=widget_attrs
        ),
    )

    self.plantas_por_unidad_json = (
        _uop_json.dumps(
            plantas_por_unidad,
            ensure_ascii=False,
        )
    )


def _uop_clean(self):
    cleaned = (
        _uop_original_clean(
            self
        )
    )

    unidad = cleaned.get(
        "unidad_obra"
    )

    planta = str(
        cleaned.get(
            "legacy_planta"
        )
        or ""
    ).strip()

    if unidad is None:
        return cleaned

    historical_unchanged = (
        _uop_historical_unchanged(
            self,
            unidad,
            planta,
        )
    )

    catalogo = (
        _UnidadObraPlanta.objects
        .filter(
            unidad_obra=unidad,
            activa=True,
        )
    )

    if not catalogo.exists():
        if historical_unchanged:
            return cleaned

        if not self._errors.get(
            "unidad_obra"
        ):
            self.add_error(
                "unidad_obra",
                (
                    "Esta unidad no tiene plantas "
                    "configuradas. Añádelas primero "
                    "en Unidades de obra."
                ),
            )

        return cleaned

    if self._errors.get(
        "legacy_planta"
    ):
        return cleaned

    planta_catalogo = (
        catalogo
        .filter(
            nombre__iexact=planta
        )
        .first()
    )

    if planta_catalogo is not None:
        cleaned[
            "legacy_planta"
        ] = planta_catalogo.nombre

        return cleaned

    if not historical_unchanged:
        self.add_error(
            "legacy_planta",
            (
                "La planta seleccionada no "
                "pertenece a esta unidad."
            ),
        )

    return cleaned


TareaObraSimpleForm.__init__ = (
    _uop_init
)

TareaObraSimpleForm.clean = (
    _uop_clean
)
