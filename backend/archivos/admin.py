from django.contrib import admin
from .models import Carpeta, Archivo


@admin.register(Carpeta)
class CarpetaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "parent", "visibilidad", "departamento", "owner", "created_at")
    list_filter = ("visibilidad", "departamento")
    search_fields = ("nombre", "departamento", "owner__username", "owner__first_name", "owner__last_name")
    autocomplete_fields = ("parent", "owner")


@admin.register(Archivo)
class ArchivoAdmin(admin.ModelAdmin):
    list_display = ("nombre_original", "carpeta", "subido_por", "tamano_mb", "created_at")
    list_filter = ("carpeta",)
    search_fields = ("nombre_original", "carpeta__nombre", "subido_por__username")
    autocomplete_fields = ("carpeta", "subido_por")
    readonly_fields = ("tamano_bytes", "created_at")
