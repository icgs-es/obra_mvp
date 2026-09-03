from django.urls import path

from . import views

app_name = "gestion"


# FACTURA_PAGADA_CERRADA_URL_GUARDS_V1
from apps.gestion.factura_cierre import instalar_guardas
_FACTURA_PAGADA_GUARDS_V1 = instalar_guardas(views)

urlpatterns = [
    # FACTURA_ABONO_CIERRE_ADMINISTRATIVO_V1
    path(
        "facturas/<int:pk>/abono-estado/",
        views.factura_abono_cambiar_estado,
        name="factura_abono_estado",
    ),

    path("albaranes/<int:albaran_pk>/lineas/nueva/", views.albaran_linea_create_compat, name="albaran_linea_create_compat"),
    path("albaranes/<int:albaran_pk>/lineas/<int:linea_pk>/eliminar/", views.albaran_linea_delete_compat, name="albaran_linea_delete_compat"),
    path("facturas/<int:pk>/importar-desde-albaran/", views.factura_importar_desde_albaran, name="factura_importar_desde_albaran"),
    path("facturas/<int:pk>/lineas/a-partida/", views.factura_lineas_a_partida, name="factura_lineas_a_partida"),
    path("albaranes/<int:pk>/lineas/a-partida/", views.albaran_lineas_a_partida, name="albaran_lineas_a_partida"),
    path("albaranes/<int:albaran_pk>/lineas/<int:linea_pk>/imputaciones/<int:real_pk>/actualizar/", views.albaran_linea_imputacion_update, name="albaran_linea_imputacion_update"),
    path("albaranes/<int:albaran_pk>/lineas/<int:linea_pk>/imputaciones/<int:real_pk>/eliminar/", views.albaran_linea_imputacion_delete, name="albaran_linea_imputacion_delete"),
    path("albaranes/<int:pk>/lineas/a-almacen/", views.albaran_lineas_a_almacen, name="albaran_lineas_a_almacen"),
    path("facturas/<int:pk>/lineas/a-almacen/", views.factura_lineas_a_almacen, name="factura_lineas_a_almacen"),
    path("ocr/plantillas/crear-rapida/", views.ocr_plantilla_create_fast_json, name="ocr_plantilla_create_fast_json"),
    path("ocr/plantillas/", views.ocr_plantillas_list, name="ocr_plantillas_list"),
    path("ocr/plantillas/<int:pk>/", views.ocr_plantilla_detail, name="ocr_plantilla_detail"),
    path("ocr/plantillas/<int:pk>/activar/", views.ocr_plantilla_toggle_activa, name="ocr_plantilla_toggle_activa"),
    path("ocr/plantillas/<int:pk>/duplicar/", views.ocr_plantilla_duplicar, name="ocr_plantilla_duplicar"),
    path("ocr/plantillas-proveedor/", views.ocr_plantillas_proveedor_json, name="ocr_plantillas_proveedor_json"),
    path("articulos/buscar/", views.articulos_compra_search, name="articulos_compra_search"),
    path("articulos/crear-rapido/", views.articulo_compra_create_fast, name="articulo_compra_create_fast"),
    path("articulos/crear-servicio-rapido/", views.articulo_servicio_create_fast, name="articulo_servicio_create_fast"),
    path("articulos/sugerencia-compra/", views.articulo_compra_sugerencia_v1a, name="articulo_compra_sugerencia_v1a"),
    path("articulos/", views.articulos_compra_list, name="articulos_compra_list"),
    path("articulos/<int:pk>/", views.articulo_compra_detail, name="articulo_compra_detail"),
    path("articulos/alias/<int:alias_id>/reasignar/", views.articulo_alias_reasignar, name="articulo_alias_reasignar"),
    path("documentos/desde-pdf/", views.documento_compra_desde_pdf_dryrun, name="documento_compra_desde_pdf_dryrun"),

    path("sync-access/", views.access_sync_view, name="gestion_sync_access"),
    path("", views.gestion_index, name="index"),
    path("facturas/", views.facturas_list, name="facturas_list"),
    path("facturas/informe/", views.facturas_informe, name="facturas_informe"),
    path("pagos/pendientes/", views.pagos_pendientes_informe, name="pagos_pendientes_informe"),
    path("proveedores/", views.proveedores_list, name="proveedores_list"),
    path("centros-coste/", views.centros_coste_list, name="centros_coste_list"),

    path("proveedores/nuevo/", views.proveedor_create, name="proveedor_create"),
    path("proveedores/<int:pk>/editar/", views.proveedor_update, name="proveedor_update"),
    path("proveedores/<int:pk>/eliminar/", views.proveedor_delete, name="proveedor_delete"),
    path("albaranes/", views.albaranes_list, name="albaranes_list"),
    path("albaranes/informe/", views.albaranes_informe, name="albaranes_informe"),
    path("albaranes/desde-pdf/", views.albaran_desde_pdf, name="albaran_desde_pdf"),
    path("albaranes/nuevo/", views.albaran_create, name="albaran_create"),
    path("albaranes/<int:pk>/editar/", views.albaran_update, name="albaran_update"),
    path("albaranes/<int:pk>/eliminar/", views.albaran_delete, name="albaran_delete"),
    path("facturas/desde-pdf/", views.factura_desde_pdf, name="factura_desde_pdf"),
    path("facturas/nueva/", views.factura_create, name="factura_create"),
    path("facturas/<int:pk>/editar/", views.factura_update, name="factura_update"),
    path("facturas/<int:pk>/eliminar/", views.factura_delete, name="factura_delete"),
    path("facturas/desde-albaranes/", views.factura_desde_albaranes, name="factura_desde_albaranes"),
    path("facturas/<int:pk>/lineas/desde-ocr/", views.factura_lineas_desde_ocr, name="factura_lineas_desde_ocr"),
    path("facturas/<int:pk>/lineas/desde-ocr/crear-plantilla/", views.factura_ocr_crear_plantilla_desde_lineas, name="factura_ocr_crear_plantilla_desde_lineas"),
    path("facturas/<int:factura_id>/lineas/nueva/", views.factura_linea_create, name="factura_linea_create"),
    path("facturas/<int:factura_id>/lineas/<int:linea_id>/editar/", views.factura_linea_update, name="factura_linea_update"),
    path("facturas/<int:factura_id>/lineas/<int:linea_id>/eliminar/", views.factura_linea_delete, name="factura_linea_delete"),
    path("adjuntos/<int:adjunto_id>/ver/", views.compra_adjunto_ver, name="compra_adjunto_ver"),
    path("facturas/<int:pk>/adjuntos/subir/", views.factura_adjunto_upload, name="factura_adjunto_upload"),
    path("facturas/<int:factura_id>/adjuntos/<int:adjunto_id>/eliminar/", views.factura_adjunto_delete, name="factura_adjunto_delete"),
    path("facturas/<int:factura_id>/albaranes/<int:vinculo_id>/desvincular/", views.factura_albaran_desvincular, name="factura_albaran_desvincular"),
    # FACTURACION_AYUDA_URL_V1C
    path(
        "facturacion/ayuda/",
        views.facturacion_ayuda,
        name="facturacion_ayuda",
    ),
    # FACTURA_PAGOS_MULTIPLES_URLS_V1
    path(
        "facturas/<int:pk>/pagos/plan/",
        views.factura_plan_pagos,
        name="factura_plan_pagos",
    ),
    path(
        "facturas/<int:pk>/pagos/<int:vencimiento_id>/pagado/",
        views.factura_vencimiento_marcar_pagado,
        name="factura_vencimiento_marcar_pagado",
    ),
    path(
        "facturas/<int:pk>/pagos/corregir-estado/",
        views.factura_corregir_estado_pago,
        name="factura_corregir_estado_pago",
    ),
    path(
        "facturas/<int:pk>/pagos/revertir-erroneo/",
        views.factura_revertir_pago_erroneo,
        name="factura_revertir_pago_erroneo",
    ),
    path("facturas/<int:pk>/", views.factura_detail, name="factura_detail"),
    path("albaranes/<int:pk>/lineas/desde-ocr/", views.albaran_lineas_desde_ocr, name="albaran_lineas_desde_ocr"),
    path("albaranes/<int:albaran_id>/lineas/nueva/", views.albaran_linea_create, name="albaran_linea_create"),
    path("albaranes/<int:albaran_id>/lineas/<int:linea_id>/editar/", views.albaran_linea_update, name="albaran_linea_update"),
    path("albaranes/<int:albaran_id>/lineas/<int:linea_id>/eliminar/", views.albaran_linea_delete, name="albaran_linea_delete"),
    path("albaranes/<int:pk>/adjuntos/subir/", views.albaran_adjunto_upload, name="albaran_adjunto_upload"),
    path("albaranes/<int:albaran_id>/adjuntos/<int:adjunto_id>/eliminar/", views.albaran_adjunto_delete, name="albaran_adjunto_delete"),
    path("albaranes/<int:pk>/", views.albaran_detail, name="albaran_detail"),
    path("facturas/<int:pk>/recalcular-lineas/", views.factura_recalcular_desde_lineas, name="factura_recalcular_desde_lineas"),
    path("albaranes/<int:pk>/recalcular-lineas/", views.albaran_recalcular_desde_lineas, name="albaran_recalcular_desde_lineas"),
    path("facturas/<int:pk>/anular/", views.factura_anular, name="factura_anular"),
]
