from django.contrib import admin

from .models import (
    Comparativa,
    DocumentoComparativa,
    Oferta,
    Ofertante,
)


class OfertaInline(admin.TabularInline):
    model = Oferta
    extra = 0


@admin.register(Comparativa)
class ComparativaAdmin(admin.ModelAdmin):
    list_display = (
        "titulo",
        "categoria",
        "team",
        "estado",
        "referencia_nombre",
        "updated_at",
    )
    list_filter = (
        "estado",
        "team",
        "categoria",
    )
    search_fields = (
        "titulo",
        "categoria",
        "referencia_nombre",
        "referencia_codigo",
    )


@admin.register(Ofertante)
class OfertanteAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "comparativa",
        "tipo",
        "estado",
        "proveedor_ref_id",
    )
    list_filter = (
        "tipo",
        "estado",
    )
    search_fields = (
        "nombre",
        "nif",
    )
    inlines = (OfertaInline,)


@admin.register(Oferta)
class OfertaAdmin(admin.ModelAdmin):
    list_display = (
        "ofertante",
        "version",
        "fecha_documento",
        "base",
        "total",
        "estado",
    )
    list_filter = ("estado",)
    search_fields = (
        "ofertante__nombre",
        "referencia",
    )


@admin.register(DocumentoComparativa)
class DocumentoComparativaAdmin(
    admin.ModelAdmin
):
    list_display = (
        "nombre_original",
        "oferta",
        "content_type",
        "tamano_bytes",
        "estado_analisis",
        "created_at",
    )
    list_filter = (
        "estado_analisis",
        "extension",
    )
    search_fields = (
        "nombre_original",
        "sha256",
    )
