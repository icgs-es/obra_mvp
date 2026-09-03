from django.contrib import admin
from .models import Proveedor


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = (
        "nombre_comercial",
        "nombre_fiscal",
        "cif",
        "telefono",
        "email",
        "es_subcontrata",
        "fuera_listado",
        "team",
    )
    list_filter = ("team", "es_subcontrata", "fuera_listado", "activo", "sp_iva")
    search_fields = (
        "nombre_comercial",
        "nombre_fiscal",
        "cif",
        "telefono",
        "email",
        "legacy_id_proveedor",
    )
    readonly_fields = ("created_at", "updated_at")


from .models import EmpresaGestionLegacy


@admin.register(EmpresaGestionLegacy)
class EmpresaGestionLegacyAdmin(admin.ModelAdmin):
    list_display = (
        "legacy_id_empresa",
        "nombre_empresa",
        "cif_empresa",
        "team",
        "periodo_gestion",
        "prefijo_factura",
        "prefijo_albaran",
    )
    list_filter = ("team", "periodo_gestion")
    search_fields = ("nombre_empresa", "cif_empresa", "legacy_id_empresa")
    readonly_fields = ("created_at", "updated_at")


from .models import FacturaProveedorGestion


@admin.register(FacturaProveedorGestion)
class FacturaProveedorGestionAdmin(admin.ModelAdmin):
    list_display = (
        "cod_factura",
        "num_factura_proveedor",
        "proveedor",
        "team",
        "fecha_emision",
        "importe_factura",
        "importe_pagado",
        "estado",
        "empresa_legacy_raw",
    )
    list_filter = ("team", "estado", "empresa_legacy_raw", "tiene_retencion", "certificada")
    search_fields = (
        "cod_factura",
        "num_factura_proveedor",
        "proveedor__nombre_comercial",
        "proveedor__cif",
        "archivo",
        "archivo1",
    )
    readonly_fields = ("created_at", "updated_at")


from .models import AlbaranProveedorGestion


@admin.register(AlbaranProveedorGestion)
class AlbaranProveedorGestionAdmin(admin.ModelAdmin):
    list_display = (
        "cod_albaran",
        "num_albaran_proveedor",
        "proveedor",
        "team",
        "fecha_albaran",
        "importe_albaran",
        "asignado_factura",
        "empresa_legacy_raw",
    )
    list_filter = (
        "team",
        "empresa_legacy_raw",
        "asignado_factura",
        "asignado_partida_obra",
        "autorizado_jefe_obra",
    )
    search_fields = (
        "cod_albaran",
        "num_albaran_proveedor",
        "proveedor__nombre_comercial",
        "proveedor__cif",
        "descripcion",
        "archivo",
    )
    readonly_fields = ("created_at", "updated_at")


from .models import FacturaProveedorLineaGestion, AlbaranProveedorLineaGestion


@admin.register(FacturaProveedorLineaGestion)
class FacturaProveedorLineaGestionAdmin(admin.ModelAdmin):
    list_display = ("factura", "linea", "cod_articulo_legacy", "cantidad", "precio_unitario", "importe_linea", "en_partida", "en_almacen")
    list_filter = ("en_partida", "en_almacen")
    search_fields = ("factura__cod_factura", "cod_albaran_legacy", "cod_articulo_legacy")


@admin.register(AlbaranProveedorLineaGestion)
class AlbaranProveedorLineaGestionAdmin(admin.ModelAdmin):
    list_display = ("albaran", "linea", "cod_articulo_legacy", "cantidad", "unidad", "precio_unitario", "importe_linea", "facturado", "en_partida")
    list_filter = ("facturado", "en_pedido", "en_partida", "en_almacen")
    search_fields = ("albaran__cod_albaran", "factura_legacy", "cod_articulo_legacy", "observaciones")



from .models import FacturaAlbaranGestion


@admin.register(FacturaAlbaranGestion)
class FacturaAlbaranGestionAdmin(admin.ModelAdmin):
    list_display = ("factura", "albaran", "team", "importe_asignado", "created_at")
    list_filter = ("team",)
    search_fields = (
        "factura__cod_factura",
        "factura__num_factura_proveedor",
        "albaran__cod_albaran",
        "albaran__num_albaran_proveedor",
        "albaran__proveedor__nombre_comercial",
    )
    readonly_fields = ("created_at", "updated_at")


# === OCR_PLANTILLAS_PROVEEDOR_ADMIN_V1 ===
try:
    from .models import PlantillaOCRProveedor

    @admin.register(PlantillaOCRProveedor)
    class PlantillaOCRProveedorAdmin(admin.ModelAdmin):
        list_display = (
            "id",
            "team",
            "proveedor",
            "tipo_documento",
            "nombre",
            "variante",
            "parser_key",
            "valorado_default",
            "activa",
            "prioridad",
        )
        list_filter = ("team", "tipo_documento", "activa", "valorado_default")
        search_fields = (
            "proveedor__nombre_comercial",
            "proveedor__nombre_fiscal",
            "codigo",
            "nombre",
            "parser_key",
            "detector_texto",
        )
        ordering = ("team", "proveedor", "tipo_documento", "prioridad")
except Exception:
    pass

