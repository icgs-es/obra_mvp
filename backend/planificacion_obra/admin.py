from django.contrib import admin

from .models import (
    AlmacenObra,
    AsignacionObra,
    CapituloCatalogo,
    EmpleadoObra,
    FaseObra,
    ObraPlanificacion,
    PartidaCatalogo,
    RecursoCatalogo,
    TareaObra,
    UnidadObra,
    UnidadObraPlanta,
)


@admin.register(ObraPlanificacion)
class ObraPlanificacionAdmin(admin.ModelAdmin):
    list_display = ("legacy_cod_obra", "nombre", "team", "poblacion", "provincia", "total_viviendas")
    list_filter = ("team", "provincia")
    search_fields = ("codigo", "nombre", "descripcion", "poblacion", "provincia")
    ordering = ("legacy_cod_obra",)


@admin.register(FaseObra)
class FaseObraAdmin(admin.ModelAdmin):
    list_display = ("obra", "legacy_cod_fase", "nombre", "cantidad_viviendas", "zona_comun", "team")
    list_filter = ("team", "obra", "zona_comun")
    search_fields = ("obra__nombre", "nombre", "observaciones")
    ordering = ("obra__legacy_cod_obra", "legacy_cod_fase")


# === UNIDAD_OBRA_PLANTAS_ADMIN_V1 ===
class UnidadObraPlantaInline(admin.TabularInline):
    model = UnidadObraPlanta
    extra = 1
    fields = (
        "nombre",
        "orden",
        "activa",
    )
    ordering = (
        "orden",
        "nombre",
    )
    verbose_name = "Planta"
    verbose_name_plural = (
        "Plantas disponibles para planificación"
    )


@admin.register(UnidadObra)
class UnidadObraAdmin(admin.ModelAdmin):
    list_display = (
        "obra",
        "edificio",
        "vivienda",
        "nivel",
        "tipo",
        "team",
    )
    list_filter = (
        "team",
        "obra",
        "edificio",
        "nivel",
        "tipo",
    )
    search_fields = (
        "obra__nombre",
        "edificio",
        "vivienda",
        "nivel",
        "observaciones",
        "plantas__nombre",
    )
    ordering = (
        "obra__legacy_cod_obra",
        "edificio",
        "vivienda",
        "nivel",
    )
    inlines = (
        UnidadObraPlantaInline,
    )


@admin.register(UnidadObraPlanta)
class UnidadObraPlantaAdmin(admin.ModelAdmin):
    list_display = (
        "unidad_obra",
        "nombre",
        "orden",
        "activa",
        "team",
    )
    list_filter = (
        "team",
        "activa",
        "nombre",
    )
    search_fields = (
        "unidad_obra__obra__nombre",
        "unidad_obra__edificio",
        "unidad_obra__vivienda",
        "nombre",
    )
    ordering = (
        "unidad_obra__obra__legacy_cod_obra",
        "unidad_obra__edificio",
        "unidad_obra__vivienda",
        "orden",
        "nombre",
    )


@admin.register(CapituloCatalogo)
class CapituloCatalogoAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "orden", "team")
    list_filter = ("team",)
    search_fields = ("codigo", "nombre")
    ordering = ("orden", "codigo")


@admin.register(PartidaCatalogo)
class PartidaCatalogoAdmin(admin.ModelAdmin):
    list_display = ("capitulo", "codigo", "nombre", "tipo_partida", "unidad", "team")
    list_filter = ("team", "capitulo", "tipo_partida", "unidad")
    search_fields = ("codigo", "nombre", "capitulo__codigo", "capitulo__nombre")
    ordering = ("capitulo__codigo", "codigo")


@admin.register(RecursoCatalogo)
class RecursoCatalogoAdmin(admin.ModelAdmin):
    list_display = ("legacy_id", "nombre", "tipo", "unidad", "stock", "control_stock", "team")
    list_filter = ("team", "tipo", "unidad", "control_stock")
    search_fields = ("legacy_id", "nombre", "observaciones")
    ordering = ("tipo", "nombre")


@admin.register(EmpleadoObra)
class EmpleadoObraAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "categoria", "situacion", "precio_hora", "team")
    list_filter = ("team", "tipo", "categoria", "situacion")
    search_fields = ("nombre", "empresa_origen", "observaciones")
    ordering = ("nombre",)


@admin.register(AlmacenObra)
class AlmacenObraAdmin(admin.ModelAdmin):
    list_display = ("legacy_id_almacen", "nombre", "obra", "ubicacion", "descuenta_stock", "team")
    list_filter = ("team", "obra", "descuenta_stock")
    search_fields = ("legacy_id_almacen", "nombre", "ubicacion", "obra__nombre")
    ordering = ("obra__legacy_cod_obra", "legacy_id_almacen")


@admin.register(TareaObra)
class TareaObraAdmin(admin.ModelAdmin):
    list_display = ("legacy_key", "obra", "unidad_obra", "capitulo", "partida", "inicio_tarea", "fin_tarea", "porcentaje_completado", "team")
    list_filter = ("team", "obra", "capitulo", "inicio_tarea", "inicio_real")
    search_fields = ("legacy_key", "legacy_cod_vivienda", "legacy_capitulo", "legacy_partida", "observaciones")
    ordering = ("inicio_tarea", "legacy_cod_obra", "legacy_cod_fase", "legacy_cod_vivienda", "legacy_orden")


@admin.register(AsignacionObra)
class AsignacionObraAdmin(admin.ModelAdmin):
    list_display = ("empleado", "tarea_obra", "unidad_obra", "capitulo", "partida", "fecha_inicio", "hora_inicio", "fecha_fin", "estado", "team")
    list_filter = ("team", "estado", "fecha_inicio", "capitulo")
    search_fields = ("empleado__nombre_completo", "tarea_obra__legacy_key", "unidad_obra__edificio", "unidad_obra__vivienda", "observaciones")
    ordering = ("fecha_inicio", "hora_inicio", "empleado__nombre_completo")


from django.apps import apps as django_apps

RecursoAlmacenMovimiento = django_apps.get_model("planificacion_obra", "RecursoAlmacenMovimiento")


@admin.register(RecursoAlmacenMovimiento)
class RecursoAlmacenMovimientoAdmin(admin.ModelAdmin):
    list_display = (
        "legacy_id_movimiento",
        "fecha_movimiento",
        "tipo_movimiento",
        "legacy_id_almacen",
        "legacy_cod_recurso",
        "cantidad",
        "unidad",
        "legacy_cod_obra",
        "legacy_cod_fase",
        "legacy_cod_vivienda",
        "legacy_partida",
        "team",
    )
    list_filter = ("team", "tipo_movimiento", "fecha_movimiento", "legacy_id_almacen", "legacy_cod_obra")
    search_fields = (
        "legacy_id_movimiento",
        "legacy_id_almacen",
        "legacy_cod_recurso",
        "cod_albaran",
        "cod_factura",
        "observaciones",
    )
    readonly_fields = ("created_at", "updated_at", "raw_data")
    ordering = ("-fecha_movimiento", "-legacy_id_movimiento")


TareaRecursoPrevisto = django_apps.get_model("planificacion_obra", "TareaRecursoPrevisto")


@admin.register(TareaRecursoPrevisto)
class TareaRecursoPrevistoAdmin(admin.ModelAdmin):
    list_display = (
        "legacy_row_number",
        "legacy_cod_obra",
        "legacy_cod_fase",
        "legacy_cod_vivienda",
        "legacy_planta",
        "legacy_cod_partida",
        "legacy_id_recurso",
        "cantidad",
        "unidad",
        "precio_unidad",
        "costo_recurso",
        "legacy_orden_recurso",
        "team",
    )
    list_filter = ("team", "legacy_cod_obra", "legacy_planta", "control_suministros")
    search_fields = (
        "legacy_row_number",
        "legacy_cod_partida",
        "legacy_id_recurso",
        "legacy_cod_vivienda",
    )
    readonly_fields = ("created_at", "updated_at", "raw_data")
    ordering = (
        "legacy_cod_obra",
        "legacy_cod_fase",
        "legacy_cod_vivienda",
        "legacy_planta",
        "legacy_cod_partida",
        "legacy_orden_recurso",
    )


TareaRecursoReal = django_apps.get_model("planificacion_obra", "TareaRecursoReal")


@admin.register(TareaRecursoReal)
class TareaRecursoRealAdmin(admin.ModelAdmin):
    list_display = (
        "legacy_id_recurso_tarea",
        "legacy_cod_obra",
        "legacy_cod_fase",
        "legacy_cod_vivienda",
        "legacy_planta",
        "legacy_partida",
        "legacy_tipo_recurso",
        "legacy_id_recurso",
        "cantidad",
        "unidad",
        "horas_reales",
        "costo_recurso_real",
        "team",
    )
    list_filter = ("team", "legacy_cod_obra", "legacy_tipo_recurso", "legacy_planta")
    search_fields = (
        "legacy_id_recurso_tarea",
        "legacy_partida",
        "legacy_id_recurso",
        "legacy_cod_vivienda",
        "observaciones",
    )
    readonly_fields = ("created_at", "updated_at", "raw_data")
    ordering = (
        "legacy_cod_obra",
        "legacy_cod_fase",
        "legacy_cod_vivienda",
        "legacy_planta",
        "legacy_partida",
        "legacy_orden_recurso",
    )
