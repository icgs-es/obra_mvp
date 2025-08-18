# backend/apps/core/admin.py
from django.contrib import admin
from importlib import import_module

# Carga segura de models
try:
    m = import_module("apps.core.models")
except Exception as e:
    m = None
    import sys
    print("[admin] WARNING: no se pudieron importar los modelos:", e, file=sys.stderr)

def reg(model_name, admin_class=None):
    """Registra un modelo solo si existe; evita petar si falta algo."""
    if not m or not hasattr(m, model_name):
        return
    model = getattr(m, model_name)
    try:
        if admin_class is None:
            admin_class = type(f"{model_name}Admin", (admin.ModelAdmin,), {})
        admin.site.register(model, admin_class)
    except admin.sites.AlreadyRegistered:
        pass

def field_names(model):
    if not model:
        return set()
    return {f.name for f in model._meta.get_fields()}

class SafeAdmin(admin.ModelAdmin):
    """
    Base que calcula dinámicamente columnas, filtros y autocompletados
    solo con campos que existan en el modelo.
    """
    # Candidatos por defecto (se sobreescriben en subclases)
    CANDIDATE_LIST = ()
    CANDIDATE_FILTERS = ()
    CANDIDATE_SEARCH = ()
    CANDIDATE_ORDERING = ()
    CANDIDATE_AUTOCOMPLETE = ()

    list_display = ("id",)  # siempre válido

    def _names(self):
        return field_names(self.model)

    def get_list_display(self, request):
        names = self._names()
        extra = [f for f in getattr(self, "CANDIDATE_LIST", ()) if f in names]
        return ("id",) + tuple(extra)

    def get_list_filter(self, request):
        names = self._names()
        return [f for f in getattr(self, "CANDIDATE_FILTERS", ()) if f in names]

    def get_search_fields(self, request):
        # search_fields admite lookups (obra__codigo). Filtra grosso modo por prefijos válidos.
        candidates = getattr(self, "CANDIDATE_SEARCH", ())
        valid = []
        names = self._names()
        for s in candidates:
            base = s.split("__", 1)[0]
            if base in names:
                valid.append(s)
        return valid

    def get_ordering(self, request):
        names = self._names()
        return [f for f in getattr(self, "CANDIDATE_ORDERING", ()) if f in names] or ["id"]

    def get_autocomplete_fields(self, request):
        names = self._names()
        return tuple(f for f in getattr(self, "CANDIDATE_AUTOCOMPLETE", ()) if f in names)

# ==== Admins concretos (solo proponemos candidatos; SafeAdmin filtra lo inexistente) ====

class ObraAdmin(SafeAdmin):
    CANDIDATE_LIST = ("codigo", "nombre", "cliente", "fecha_inicio", "fecha_fin", "estado")
    CANDIDATE_SEARCH = ("codigo", "nombre", "cliente")
    CANDIDATE_ORDERING = ("codigo",)

class SubObraAdmin(SafeAdmin):
    CANDIDATE_LIST = ("obra", "codigo", "nombre", "tipo", "estado", "fecha_inicio", "fecha_fin")
    CANDIDATE_FILTERS = ("obra", "tipo", "estado")
    CANDIDATE_SEARCH = ("obra__codigo", "codigo", "nombre")
    CANDIDATE_ORDERING = ("obra", "codigo")

class CapituloAdmin(SafeAdmin):
    CANDIDATE_LIST = ("obra", "subobra", "codigo", "nombre", "orden")
    CANDIDATE_FILTERS = ("obra", "subobra")
    CANDIDATE_SEARCH = ("codigo", "nombre", "obra__codigo", "obra__nombre", "subobra__codigo", "subobra__nombre")
    CANDIDATE_ORDERING = ("obra", "subobra", "orden", "codigo")

class TareaAsPartidaAdmin(SafeAdmin):
    # Se mostrará como “Partidas” si en el modelo Tarea pones verbose_name="Partida"
    CANDIDATE_LIST = ("capitulo", "nombre", "fecha_inicio_plan", "fecha_fin_plan", "horas_plan", "coste_plan")
    CANDIDATE_FILTERS = ("capitulo__obra", "capitulo")
    CANDIDATE_SEARCH = ("nombre", "capitulo__codigo", "capitulo__obra__codigo")
    CANDIDATE_AUTOCOMPLETE = ("capitulo",)

class RecursoPersonalAdmin(SafeAdmin):
    CANDIDATE_LIST = ("nombre", "especialidad", "coste_hora", "activo")
    CANDIDATE_FILTERS = ("especialidad", "activo")
    CANDIDATE_SEARCH = ("nombre", "especialidad")

class RecursoMaterialAdmin(SafeAdmin):
    CANDIDATE_LIST = ("referencia", "nombre", "precio_ref")
    CANDIDATE_SEARCH = ("referencia", "nombre")
    CANDIDATE_ORDERING = ("referencia",)

class PlanificacionAdmin(SafeAdmin):
    CANDIDATE_LIST = ("fecha", "tarea", "tipo", "recurso_personal", "recurso_material", "horas_plan", "cantidad_plan", "importe_plan")
    CANDIDATE_FILTERS = ("tipo", "tarea__capitulo__obra", "tarea__capitulo")
    CANDIDATE_SEARCH = ("tarea__nombre", "tarea__capitulo__codigo", "tarea__capitulo__obra__codigo")
    CANDIDATE_AUTOCOMPLETE = ("tarea", "recurso_personal", "recurso_material")

class ParteTrabajoAdmin(SafeAdmin):
    CANDIDATE_LIST = ("fecha", "recurso", "obra", "capitulo", "tarea", "horas")
    CANDIDATE_FILTERS = ("obra", "capitulo")
    CANDIDATE_SEARCH = ("recurso__nombre", "obra__codigo", "capitulo__codigo", "tarea__nombre")
    CANDIDATE_AUTOCOMPLETE = ("recurso", "obra", "capitulo", "tarea")

class ProveedorAdmin(SafeAdmin):
    CANDIDATE_LIST = ("nombre", "nif")
    CANDIDATE_SEARCH = ("nombre", "nif")

class FacturaProveedorAdmin(SafeAdmin):
    CANDIDATE_LIST = ("numero", "proveedor", "obra", "capitulo", "fecha", "total", "estado")
    CANDIDATE_FILTERS = ("proveedor", "obra", "estado")
    CANDIDATE_SEARCH = ("numero", "proveedor__nombre", "obra__codigo")
    CANDIDATE_AUTOCOMPLETE = ("proveedor", "obra", "capitulo")

class VencimientoAdmin(SafeAdmin):
    CANDIDATE_LIST = ("factura", "fecha_venc", "importe", "pagado")
    CANDIDATE_FILTERS = ("pagado",)
    CANDIDATE_SEARCH = ("factura__numero", "factura__proveedor__nombre")
    CANDIDATE_AUTOCOMPLETE = ("factura",)

class AusenciaAdmin(SafeAdmin):
    CANDIDATE_LIST = ("recurso", "tipo", "fecha_inicio", "fecha_fin", "horas")  # si 'horas' no existe, se omitirá
    CANDIDATE_FILTERS = ("tipo",)
    CANDIDATE_SEARCH = ("recurso__nombre",)
    CANDIDATE_AUTOCOMPLETE = ("recurso",)

# Registro seguro (solo si el modelo existe)
reg("Obra", ObraAdmin)
reg("SubObra", SubObraAdmin)
reg("Capitulo", CapituloAdmin)
reg("Tarea", TareaAsPartidaAdmin)     # si usas proxy Partida, cambia por reg("Partida", TareaAsPartidaAdmin)
reg("RecursoPersonal", RecursoPersonalAdmin)
reg("RecursoMaterial", RecursoMaterialAdmin)
reg("Planificacion", PlanificacionAdmin)
reg("ParteTrabajo", ParteTrabajoAdmin)
reg("Proveedor", ProveedorAdmin)
reg("FacturaProveedor", FacturaProveedorAdmin)
reg("Vencimiento", VencimientoAdmin)
reg("Ausencia", AusenciaAdmin)
