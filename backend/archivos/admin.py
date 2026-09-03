from django.contrib import admin
from .models import Carpeta, Archivo, ArchivoLog


@admin.register(Carpeta)
class CarpetaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "team", "parent", "visibilidad", "departamento", "owner", "created_at")
    list_filter = ("team", "visibilidad", "departamento")
    search_fields = ("nombre", "departamento", "owner__username", "owner__first_name", "owner__last_name")
    autocomplete_fields = ("parent", "owner")


@admin.register(Archivo)
class ArchivoAdmin(admin.ModelAdmin):
    list_display = ("nombre_original", "carpeta", "subido_por", "tamano_mb", "created_at")
    list_filter = ("carpeta",)
    search_fields = ("nombre_original", "carpeta__nombre", "subido_por__username")
    autocomplete_fields = ("carpeta", "subido_por")
    readonly_fields = ("tamano_bytes", "created_at")


@admin.register(ArchivoLog)
class ArchivoLogAdmin(admin.ModelAdmin):
    list_display = ("archivo", "accion", "usuario", "fecha")
    list_filter = ("accion", "usuario")
    search_fields = ("archivo__nombre_original", "usuario__username")
    autocomplete_fields = ("archivo", "usuario")
    readonly_fields = ("fecha",)

# ARCHIVOS_RBAC_P1A_ADMIN_V1
from .models import ReglaAccesoRaizCloud


@admin.register(ReglaAccesoRaizCloud)
class ReglaAccesoRaizCloudAdmin(
    admin.ModelAdmin
):
    list_display = (
        "nombre_raiz",
        "activa",
        "visible_para_todos",
        "grupos_autorizados",
        "updated_at",
    )

    list_filter = (
        "activa",
        "visible_para_todos",
        "grupos",
    )

    search_fields = (
        "nombre_raiz",
        "descripcion",
        "grupos__name",
    )

    filter_horizontal = (
        "grupos",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "nombre_raiz",
    )

    def grupos_autorizados(
        self,
        obj,
    ):
        return ", ".join(
            obj.grupos
            .order_by("name")
            .values_list(
                "name",
                flat=True,
            )
        ) or "—"

    grupos_autorizados.short_description = (
        "Grupos autorizados"
    )

