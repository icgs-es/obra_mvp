from django.contrib import admin
from .models import Activo

@admin.register(Activo)
class ActivoAdmin(admin.ModelAdmin):
    list_display = (
        "codigo_externo",
        "origen_activo",
        "estado_operativo",
        "situacion_activo",
        "team",
        "updated_at",
    )

    search_fields = (
        "codigo_externo",
        "origen_activo",
        "gestor_principal",
        "situacion_activo",
    )

    list_filter = (
        "team",
        "origen_activo",
        "estado_operativo",
        "is_active",
    )

    ordering = ("-updated_at",)