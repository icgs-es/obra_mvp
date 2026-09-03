from . import views as obra_movil_direct_views  # OBRA_MOVIL_DIRECT_FLOW_IMPORT_OK
from . import views as obra_movil_ux1d_views  # OBRA_MOVIL_ALM_UX1D_URL_IMPORT_OK
from django.urls import path

from . import views

app_name = "obra_movil"

urlpatterns = [
    path("stock-rapido/", views.stock_rapido, name="stock_rapido"),  # STOCK_UX1A_URL_OK
    path("almacen/rapido/articulos/", obra_movil_ux1d_views.almacen_rapido_articulos_api, name="almacen_rapido_articulos_api"),  # OBRA_MOVIL_ALM_UX1D_URL_OK
    path("almacen/rapido/destino-planificacion/", views.almacen_rapido_destino_planificacion_api, name="almacen_rapido_destino_planificacion_api"),  # OBRA_MOVIL_ALM_UX2B7_DESTINO_PLANIFICACION_OK

    path("manifest.webmanifest", views.pwa_manifest, name="pwa_manifest"),
    path("icon.svg", views.pwa_icon, name="pwa_icon"),
    path("", views.index, name="index"),
    path("instalar/", views.instalar_home, name="instalar_home"),
    path("produccion/", obra_movil_direct_views.obra_movil_produccion_direct_redirect, name="produccion_home"),  # OBRA_MOVIL_DIRECT_FLOW_URL_OK
    path("produccion/nueva/", views.produccion_nueva, name="produccion_nueva"),
    path("almacen/", obra_movil_direct_views.obra_movil_almacen_direct_redirect, name="almacen_home"),  # OBRA_MOVIL_DIRECT_FLOW_URL_OK
    path("almacen/nuevo/", views.almacen_nuevo, name="almacen_nuevo"),
    path("almacen/rapido/", views.almacen_rapido, name="almacen_rapido"),
    path("stock/", views.stock_home, name="stock_home"),
    path("stock/control/", views.stock_control, name="stock_control"),
    path("stock/control/<int:recurso_pk>/", views.stock_control, name="stock_control_recurso"),
    path("mortero/", views.mortero_home, name="mortero_home"),
    path("mortero/nuevo/", views.mortero_nuevo, name="mortero_nuevo"),
    path("gasoil/", views.gasoil_home, name="gasoil_home"),
    path("gasoil/salida/", views.gasoil_salida_vehiculo, name="gasoil_salida_vehiculo"),  # GAS_UX1A_URL_OK
    path("gasoil/nuevo/", views.gasoil_nuevo, name="gasoil_nuevo"),
    path("historial/", views.historial_home, name="historial_home"),
    path("historial/produccion/<int:pk>/", views.historial_produccion_detail, name="historial_produccion_detail"),
    path("historial/movimiento/<int:pk>/", views.historial_movimiento_detail, name="historial_movimiento_detail"),
    path("incidencias/", views.incidencias_home, name="incidencias_home"),
    path("incidencias/nueva/", views.incidencia_nueva, name="incidencia_nueva"),
    path("incidencias/<int:pk>/", views.incidencia_detail, name="incidencia_detail"),

    path("almacen/movimientos/", views.almacen_movimientos_desktop_redirect, name="almacen_movimientos"),
    path("almacen/movimientos/<int:pk>/editar/", views.almacen_movimiento_editar, name="almacen_movimiento_editar"),  # ALM_MOV_UX1A_EDIT_URL_OK
    path("almacen/movimientos/<int:pk>/eliminar/", views.almacen_movimiento_eliminar, name="almacen_movimiento_eliminar"),  # ALM_MOV_UX1A_DELETE_URL_OK
    path("almacen/movimientos/<int:pk>/imputar/", views.almacen_movimiento_imputar, name="almacen_movimiento_imputar"),
]

# FIX_OBRA_MOVIL_DIRECT_FLOW_SYNTAX_OK
