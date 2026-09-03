from django.contrib import admin

from .models import Empleado, GrupoTrabajo, EmpleadoGrupoTrabajo


class EmpleadoGrupoTrabajoInline(admin.TabularInline):
    model = EmpleadoGrupoTrabajo
    extra = 0
    autocomplete_fields = ["grupo"]


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre_completo",
        "team",
        "area_principal",
        "tipo_relacion",
        "situacion",
        "empresa_empleadora",
        "user",
        "activo",
    )
    list_filter = (
        "team",
        "area_principal",
        "tipo_relacion",
        "situacion",
        "activo",
        "es_planificable_obra",
        "es_fichable",
    )
    search_fields = (
        "nombre_completo",
        "nif_nie",
        "telefono",
        "email",
        "codigo",
        "empresa_empleadora",
    )
    autocomplete_fields = ["user"]
    inlines = [EmpleadoGrupoTrabajoInline]


@admin.register(GrupoTrabajo)
class GrupoTrabajoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "team", "tipo", "activo")
    list_filter = ("team", "tipo", "activo")
    search_fields = ("nombre", "descripcion")


@admin.register(EmpleadoGrupoTrabajo)
class EmpleadoGrupoTrabajoAdmin(admin.ModelAdmin):
    list_display = ("empleado", "grupo", "rol", "activo", "fecha_inicio", "fecha_fin")
    list_filter = ("grupo__team", "grupo__tipo", "activo")
    search_fields = ("empleado__nombre_completo", "grupo__nombre", "rol")
    autocomplete_fields = ["empleado", "grupo"]

# ============================================================================
# RRHH_SELECCION_PERSONAL_V1
# ============================================================================

from .models import (
    Candidato,
    Candidatura,
    CandidaturaSeguimiento,
    ProcesoSeleccion,
)


class CandidaturaSeguimientoInline(admin.TabularInline):
    model = CandidaturaSeguimiento
    extra = 0
    readonly_fields = ("creado_en",)
    autocomplete_fields = ("usuario",)


@admin.register(ProcesoSeleccion)
class ProcesoSeleccionAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "team",
        "area",
        "estado",
        "responsable",
        "fecha_apertura",
        "fecha_cierre",
    )
    list_filter = ("team", "area", "estado")
    search_fields = ("titulo", "descripcion", "requisitos")
    autocomplete_fields = ("responsable", "creado_por", "modificado_por")


@admin.register(Candidato)
class CandidatoAdmin(admin.ModelAdmin):
    list_display = (
        "nombre_completo",
        "team",
        "perfil_profesional",
        "ciudad",
        "email",
        "telefono",
        "activo",
    )
    list_filter = ("team", "activo", "ciudad")
    search_fields = (
        "nombre_completo",
        "email",
        "telefono",
        "perfil_profesional",
        "ciudad",
    )
    autocomplete_fields = ("creado_por",)


@admin.register(Candidatura)
class CandidaturaAdmin(admin.ModelAdmin):
    list_display = (
        "candidato",
        "proceso",
        "estado",
        "puntuacion",
        "responsable",
        "fecha_solicitud",
        "fecha_proximo_contacto",
        "fecha_entrevista",
    )
    list_filter = (
        "proceso__team",
        "proceso",
        "estado",
        "origen",
        "puntuacion",
    )
    search_fields = (
        "candidato__nombre_completo",
        "candidato__email",
        "candidato__telefono",
        "proceso__titulo",
        "observaciones_revision",
        "observaciones_entrevista",
    )
    autocomplete_fields = (
        "proceso",
        "candidato",
        "responsable",
        "creado_por",
        "modificado_por",
    )
    raw_id_fields = ("cv_archivo",)
    inlines = (CandidaturaSeguimientoInline,)


@admin.register(CandidaturaSeguimiento)
class CandidaturaSeguimientoAdmin(admin.ModelAdmin):
    list_display = ("candidatura", "tipo", "fecha", "completado", "usuario")
    list_filter = ("tipo", "completado", "candidatura__proceso__team")
    search_fields = (
        "candidatura__candidato__nombre_completo",
        "notas",
        "resultado",
    )
    autocomplete_fields = ("candidatura", "usuario")
