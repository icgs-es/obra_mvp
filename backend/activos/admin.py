from django.contrib import admin
from .models import ActivoCore


@admin.register(ActivoCore)
class ActivoCoreAdmin(admin.ModelAdmin):
    list_display = (
        "codigo_externo",
        "nombre",
        "tipo_activo",
        "origen_activo",
        "estado_operativo",
        "situacion_activo",
        "crm_disponible",
        "crm_activo",
        "team",
        "updated_at",
    )

    search_fields = (
        "codigo_externo",
        "nombre",
        "origen_activo",
        "gestor_principal",
        "situacion_activo",
        "direccion",
        "ciudad",
        "provincia",
    )

    list_filter = (
        "team",
        "tipo_activo",
        "origen_sistema",
        "origen_activo",
        "estado_operativo",
        "crm_disponible",
        "crm_activo",
        "is_active",
        "sync_ok",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "fecha_sync",
    )

    fieldsets = (
        ("Identificación", {
            "fields": (
                "team",
                "nombre",
                "codigo_externo",
                "row_id_externo",
                "tipo_activo",
            )
        }),
        ("Origen y sincronización", {
            "fields": (
                "origen_sistema",
                "base_origen",
                "tabla_origen",
                "origen_activo",
                "fecha_sync",
                "sync_hash",
                "sync_ok",
            )
        }),
        ("Estado", {
            "fields": (
                "estado_operativo",
                "estado_operativo_raw",
                "situacion_activo",
                "gestor_principal",
                "gestores_raw",
                "historial_resumen",
            )
        }),
        ("Ubicación", {
            "fields": (
                "direccion",
                "ciudad",
                "provincia",
                "codigo_postal",
                "pais",
            )
        }),
        ("Relaciones externas (raw)", {
            "fields": (
                "valoraciones_raw",
                "visitas_raw",
                "cargas_raw",
                "demandas_raw",
            )
        }),
        ("CRM", {
            "fields": (
                "crm_disponible",
                "crm_activo",
            )
        }),
        ("Observaciones y control", {
            "fields": (
                "observaciones",
                "is_active",
                "created_at",
                "updated_at",
            )
        }),
    )

    ordering = ("-updated_at", "codigo_externo")