from django.contrib import admin

from .models import IncidenciaObraMovil


# OBRA_MOVIL_ADMIN_INCIDENCIAS_V1
class IncidenciaObraMovilAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "fecha",
        "estado",
        "prioridad",
        "tipo",
        "titulo",
        "obra",
        "unidad_obra",
        "empleado",
        "created_by",
        "created_at",
    )
    list_filter = (
        "team",
        "estado",
        "prioridad",
        "tipo",
        "fecha",
        "obra",
    )
    search_fields = (
        "id",
        "titulo",
        "descripcion",
        "resolucion",
        "obra__nombre",
        "unidad_obra__edificio",
        "unidad_obra__vivienda",
        "empleado__nombre",
    )
    readonly_fields = (
        "raw_data",
        "created_at",
        "updated_at",
        "closed_at",
    )
    # OBRA_MOVIL_ADMIN_RAW_ID_V2
    # raw_id_fields evita depender de search_fields en los ModelAdmin relacionados.
    raw_id_fields = (
        "team",
        "obra",
        "unidad_obra",
        "tarea_obra",
        "empleado",
        "created_by",
        "closed_by",
    )
    date_hierarchy = "fecha"
    ordering = ("-fecha", "-id")


if not admin.site.is_registered(IncidenciaObraMovil):
    admin.site.register(IncidenciaObraMovil, IncidenciaObraMovilAdmin)
