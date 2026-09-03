from django.urls import path
from . import views_access_sync
from . import views

app_name = "planificacion_obra"

urlpatterns = [
    path("almacen/movimientos/", views.almacen_movimientos_list, name="almacen_movimientos_list"),
    path("almacen/movimientos/general/", views.almacen_movimientos_general, name="almacen_movimientos_general"),
    path("almacen/movimientos/general/", views.almacen_movimientos_general, name="almacen_movimientos_general"),
    path("almacen/movimientos/<int:pk>/imputar/", views.almacen_movimiento_imputar_partida, name="almacen_movimiento_imputar_partida"),
    
    path("viviendas/estado/", views.vivienda_estado, name="vivienda_estado"),
path("sync-access/", views_access_sync.sync_access_planificacion, name="sync_access_planificacion"),
    path("access-sync/", views_access_sync.access_sync_verify, name="access_sync_verify"),
    path("tareas/nueva/", views.tarea_manual_create, name="tarea_manual_create"),
    path("obras/<int:obra_pk>/tareas/nueva/", views.tarea_manual_create, name="obra_tarea_manual_create"),
    path("planning/tareas/<int:pk>/editar/", views.tarea_manual_update, name="tarea_manual_update"),
    path("planning/tareas/<int:pk>/eliminar/", views.tarea_manual_delete, name="tarea_manual_delete"),
    path("planning/tareas/<int:pk>/recursos/previstos/nuevo/", views.tarea_recurso_previsto_create, name="tarea_recurso_previsto_create"),
    path("planning/tareas/recursos/previstos/<int:pk>/editar/", views.tarea_recurso_previsto_update, name="tarea_recurso_previsto_update"),
    path("planning/tareas/recursos/previstos/<int:pk>/eliminar/", views.tarea_recurso_previsto_delete, name="tarea_recurso_previsto_delete"),
    path("planning/tareas/recursos/previstos/<int:pk>/reubicar/", views.tarea_recurso_previsto_reubicar, name="tarea_recurso_previsto_reubicar"),
    path("planning/tareas/<int:pk>/recursos/reales/nuevo/", views.tarea_recurso_real_create, name="tarea_recurso_real_create"),
    path("planning/tareas/recursos/reales/<int:pk>/editar/", views.tarea_recurso_real_update, name="tarea_recurso_real_update"),
    path("planning/tareas/recursos/reales/<int:pk>/eliminar/", views.tarea_recurso_real_delete, name="tarea_recurso_real_delete"),
    # TAREA_RECURSO_REAL_REUBICAR_URL_V1_2
    path(
        "planning/tareas/recursos/reales/<int:pk>/reubicar/",
        views.tarea_recurso_real_reubicar,
        name="tarea_recurso_real_reubicar",
    ),
    path("planning/tareas/<int:pk>/", views.planning_tarea_detail, name="planning_tarea_detail"),
    path("planning/", views.planning_list, name="planning_list"),
    path("materiales-asignados/", views.materiales_asignados_report, name="materiales_asignados"),
    path("materiales-asignados/imprimir/", views.materiales_asignados_print, name="materiales_asignados_print"),
    path("materiales-asignados.csv", views.materiales_asignados_csv, name="materiales_asignados_csv"),

    # RECURSOS_OBRA_URL_V1
    path(
        "recursos/",
        views.recursos_obra_list,
        name="recursos_obra_list",
    ),

    path("asignaciones/calendario/", views.asignaciones_calendario, name="asignaciones_calendario"),
    path("asignaciones/gantt/", views.asignaciones_gantt, name="asignaciones_gantt"),
    path("asignaciones/informe/", views.asignaciones_informe, name="asignaciones_informe"),
    path("asignaciones/calendario/feed/", views.asignaciones_calendario_feed, name="asignaciones_calendario_feed"),
    path("asignaciones/calendario/filtros/", views.asignaciones_calendario_filtros, name="asignaciones_calendario_filtros"),


    path("realizados/<int:pk>/", views.realizado_detail, name="realizado_detail"),
    path("realizados/<int:pk>/editar/", views.realizado_update, name="realizado_update"),

    path("asignaciones/<int:pk>/realizar/", views.asignacion_realizar, name="asignacion_realizar"),
    path("asignaciones/<int:pk>/repetir/", views.asignacion_repetir, name="asignacion_repetir"),
    path("asignaciones/<int:pk>/", views.asignacion_detail, name="asignacion_detail"),
    path("asignaciones/<int:pk>/editar/", views.asignacion_update, name="asignacion_update"),
    path("asignaciones/<int:pk>/eliminar/", views.asignacion_delete, name="asignacion_delete"),

    path("asignaciones/opciones/", views.pi_opciones_endpoint_final_sin_nivel, name="asignaciones_opciones_final"),
    path("", views.index, name="index"),
    path("asignaciones/", views.asignaciones_list, name="asignaciones_list"),
    path("asignaciones/nueva/", views.asignacion_create, name="asignacion_create"),
    path("asignaciones/opciones/", views.asignacion_estructura_options, name="asignacion_estructura_options"),
    path("obras/", views.obras_list, name="obras_list"),
    path("obras/<int:pk>/tareas/", views.obra_tareas_list, name="obra_tareas_list"),
    path("obras/<int:pk>/", views.obra_detail, name="obra_detail"),
    path("informes/<str:filename>/", views.descargar_informe, name="descargar_informe"),
]


# ASIGNACION_AVANCE_URLS_V1_1
from django.urls import path as _avance_path

urlpatterns += [
    _avance_path(
        "asignaciones/tarea-avance/<int:pk>/",
        views.asignacion_tarea_avance_api,
        name="asignacion_tarea_avance_api",
    ),
    _avance_path(
        "tareas/<int:pk>/avance/",
        views.tarea_avance_update,
        name="tarea_avance_update",
    ),
]
