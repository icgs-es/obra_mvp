
from django.contrib import admin
from .models import (
    Obra, Capitulo, Tarea,
    RecursoPersonal, RecursoMaterial,
    Planificacion, ParteTrabajo,
    Proveedor, FacturaProveedor, Vencimiento,
    Ausencia
)

@admin.register(Obra)
class ObraAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "cliente", "fecha_inicio", "fecha_fin", "estado")
    search_fields = ("codigo", "nombre", "cliente")
    ordering = ("codigo",)

@admin.register(Capitulo)
class CapituloAdmin(admin.ModelAdmin):
    list_display = ("obra", "codigo", "nombre", "orden")
    search_fields = ("codigo", "nombre", "obra__codigo", "obra__nombre")
    list_filter = ("obra",)
    ordering = ("obra", "orden", "codigo")

@admin.register(Tarea)
class TareaAdmin(admin.ModelAdmin):
    list_display = ("capitulo", "nombre", "fecha_inicio_plan", "fecha_fin_plan", "horas_plan", "coste_plan")
    search_fields = ("nombre", "capitulo__codigo", "capitulo__obra__codigo")
    list_filter = ("capitulo__obra", "capitulo")
    autocomplete_fields = ("capitulo",)

@admin.register(RecursoPersonal)
class RecursoPersonalAdmin(admin.ModelAdmin):
    list_display = ("nombre", "especialidad", "coste_hora", "activo")
    search_fields = ("nombre", "especialidad")
    list_filter = ("especialidad", "activo")

@admin.register(RecursoMaterial)
class RecursoMaterialAdmin(admin.ModelAdmin):
    list_display = ("referencia", "nombre", "precio_ref")
    search_fields = ("referencia", "nombre")
    ordering = ("referencia",)

@admin.register(Planificacion)
class PlanificacionAdmin(admin.ModelAdmin):
    list_display = ("fecha", "tarea", "tipo", "recurso_personal", "recurso_material", "horas_plan", "cantidad_plan", "importe_plan")
    search_fields = ("tarea__nombre", "tarea__capitulo__codigo", "tarea__capitulo__obra__codigo")
    list_filter = ("tipo", "tarea__capitulo__obra", "tarea__capitulo")
    autocomplete_fields = ("tarea", "recurso_personal", "recurso_material")
    date_hierarchy = "fecha"

@admin.register(ParteTrabajo)
class ParteTrabajoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "recurso", "obra", "capitulo", "tarea", "horas")
    search_fields = ("recurso__nombre", "obra__codigo", "capitulo__codigo", "tarea__nombre")
    list_filter = ("obra", "capitulo")
    date_hierarchy = "fecha"
    autocomplete_fields = ("recurso", "obra", "capitulo", "tarea")

@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ("nombre", "nif")
    search_fields = ("nombre", "nif")

@admin.register(FacturaProveedor)
class FacturaProveedorAdmin(admin.ModelAdmin):
    list_display = ("numero", "proveedor", "obra", "capitulo", "fecha", "total", "estado")
    search_fields = ("numero", "proveedor__nombre", "obra__codigo")
    list_filter = ("proveedor", "obra", "estado")
    date_hierarchy = "fecha"
    autocomplete_fields = ("proveedor", "obra", "capitulo")

@admin.register(Vencimiento)
class VencimientoAdmin(admin.ModelAdmin):
    list_display = ("factura", "fecha_venc", "importe", "pagado")
    search_fields = ("factura__numero", "factura__proveedor__nombre")
    list_filter = ("pagado",)
    date_hierarchy = "fecha_venc"
    autocomplete_fields = ("factura",)

@admin.register(Ausencia)
class AusenciaAdmin(admin.ModelAdmin):
    list_display = ("recurso", "tipo", "fecha_inicio", "fecha_fin", "horas")
    search_fields = ("recurso__nombre",)
    list_filter = ("tipo",)
    date_hierarchy = "fecha_inicio"
    autocomplete_fields = ("recurso",)
