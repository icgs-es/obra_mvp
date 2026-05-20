from django.urls import path
from . import views_access_sync
from . import views

app_name = "planificacion_obra"

urlpatterns = [
    path("access-sync/", views_access_sync.access_sync_verify, name="access_sync_verify"),
    path("planning/tareas/<int:pk>/", views.planning_tarea_detail, name="planning_tarea_detail"),
    path("planning/", views.planning_list, name="planning_list"),

    path("asignaciones/calendario/", views.asignaciones_calendario, name="asignaciones_calendario"),
    path("asignaciones/gantt/", views.asignaciones_gantt, name="asignaciones_gantt"),
    path("asignaciones/informe/", views.asignaciones_informe, name="asignaciones_informe"),
    path("asignaciones/calendario/feed/", views.asignaciones_calendario_feed, name="asignaciones_calendario_feed"),
    path("asignaciones/calendario/filtros/", views.asignaciones_calendario_filtros, name="asignaciones_calendario_filtros"),


    path("realizados/<int:pk>/", views.realizado_detail, name="realizado_detail"),

    path("asignaciones/<int:pk>/realizar/", views.asignacion_realizar, name="asignacion_realizar"),
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
