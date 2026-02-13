from django.urls import path
from . import views
from . import views_calendar 

app_name = "fichajes"

urlpatterns = [
    path("mi-jornada/", views.mi_jornada, name="mi_jornada"),
    path("fichar/", views.fichar, name="fichar"),
    path("mis-fichajes/", views.mis_fichajes, name="mis_fichajes"),

    # 👉 NUEVO: Terminal de fichaje para tablet
    path("terminal/", views.terminal_fichaje, name="terminal_fichaje"),

    # Informe en HTML
    path("informe/", views.informe_control_horario, name="informe_control_horario"),

    # 👉 NUEVO: descarga CSV
    path(
        "informe/csv/",
        views.informe_control_horario_csv,
        name="informe_control_horario_csv",
    ),
    path("ausencias/", views.ausencias_list, name="ausencias_list"),
    path("ausencias/nueva/", views.ausencia_create, name="ausencia_create"),
    path("ausencias/<int:pk>/editar/", views.ausencia_edit, name="ausencia_edit"),
    path(
        "ausencias/informe/pdf/",
        views.informe_ausencias_pdf,
        name="informe_ausencias_pdf",
    ),
    path(
        "ausencias/informe/csv/",
        views.informe_ausencias_csv,
        name="informe_ausencias_csv",
    ),
    # si aún no la tienes:
    path(
        "ausencias/informe/empleado/",
        views.informe_ausencias_empleado_pdf,
        name="informe_ausencias_empleado_pdf",
    ),
    path(
        "ausencias/informe/empleado/<int:user_id>/",
        views.informe_ausencias_empleado_pdf,
        name="informe_ausencias_empleado_pdf_id",
    ),
    path(
        "ausencias/calendario/",
        views_calendar.calendario_ausencias,
        name="calendario_ausencias",
    ),
    path(
        "api/ausencias/events/",
        views_calendar.ausencias_events,
        name="api_ausencias_events",
    ),
    path(
        "pdf/hoy/",
        views.informe_fichajes_hoy_pdf,
        name="fichajes_pdf_hoy",
    ),
    # PDF fichajes por rango (usuario actual)
    path(
        "pdf/rango/",
        views.informe_fichajes_rango_pdf,
        name="fichajes_pdf_rango",
    ),

    # PDF fichajes por rango para un empleado concreto (solo staff)
    path(
        "pdf/rango/empleado/<int:user_id>/",
        views.informe_fichajes_rango_pdf,
        name="fichajes_pdf_rango_empleado",
    ),
    path(
        "terminal/resumen/",
        views.terminal_resumen_hoy,
        name="terminal_resumen_hoy",
    ),
]