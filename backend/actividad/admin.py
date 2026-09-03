from django.contrib import admin

from .models import ActividadPlataforma


@admin.register(ActividadPlataforma)
class ActividadPlataformaAdmin(admin.ModelAdmin):
    list_display = (
        "ocurrida_en",
        "actor",
        "team",
        "modulo",
        "accion",
        "objeto_repr",
        "visibilidad",
        "visible_en_dashboard",
    )

    list_filter = (
        "modulo",
        "accion",
        "visibilidad",
        "origen",
        "visible_en_dashboard",
        "team",
    )

    search_fields = (
        "objeto_repr",
        "descripcion",
        "tipo_objeto",
        "actor__username",
        "team__name",
    )

    readonly_fields = (
        "team",
        "actor",
        "modulo",
        "accion",
        "tipo_objeto",
        "objeto_id",
        "objeto_repr",
        "descripcion",
        "url",
        "visibilidad",
        "origen",
        "metadata",
        "agrupacion_key",
        "clave_idempotencia",
        "visible_en_dashboard",
        "ocurrida_en",
        "created_at",
    )

    date_hierarchy = "ocurrida_en"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser and obj is None

    def has_delete_permission(self, request, obj=None):
        return False
