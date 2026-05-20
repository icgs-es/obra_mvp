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
            .filter(situacion__iexact="ACTIVO", fecha_baja__isnull=True)
        )

        if self.request_user and getattr(self.request_user, "is_authenticated", False):
            user_team_ids = list(self.request_user.teams.values_list("id", flat=True))
            if user_team_ids:
                empleados_obra = empleados_obra.filter(team_id__in=user_team_ids)

        empleado_ids_validos = empleados_obra.values_list("rrhh_empleado_id", flat=True)

        empleados = Empleado.objects.filter(id__in=empleado_ids_validos)

        emp_fields = model_fields(Empleado)

        if "activo" in emp_fields:
            empleados = empleados.filter(activo=True)

        if "es_planificable_obra" in emp_fields:
            empleados = empleados.filter(es_planificable_obra=True)

        # Si se edita una asignación antigua con empleado fuera de regla,
        # se conserva visible para no romper el formulario existente.
        if getattr(self.instance, "empleado_id", None):
            empleados = Empleado.objects.filter(
                Q(id__in=empleados.values_list("id", flat=True)) |
                Q(id=self.instance.empleado_id)
            )

        self.fields["empleado"].queryset = empleados.order_by("nombre_completo", "id")

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

