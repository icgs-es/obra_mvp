from django.urls import path

from . import views

app_name = "rrhh"

urlpatterns = [
    path("empleados/", views.empleados_list, name="empleados_list"),
    path("empleados/nuevo/", views.empleado_create, name="empleado_create"),
    path("empleados/<int:pk>/", views.empleado_detail, name="empleado_detail"),
    path("empleados/<int:pk>/editar/", views.empleado_edit, name="empleado_edit"),
]

# RRHH_SELECCION_PERSONAL_V1
urlpatterns += [
    path("seleccion/", views.seleccion_personal_list, name="seleccion_personal_list"),
    path(
        "seleccion/procesos/nuevo/",
        views.proceso_seleccion_create,
        name="proceso_seleccion_create",
    ),
    path(
        "seleccion/procesos/<int:pk>/",
        views.proceso_seleccion_detail,
        name="proceso_seleccion_detail",
    ),
    path(
        "seleccion/procesos/<int:pk>/editar/",
        views.proceso_seleccion_edit,
        name="proceso_seleccion_edit",
    ),
    path(
        "seleccion/candidaturas/nueva/",
        views.candidatura_create,
        name="candidatura_create",
    ),
    path(
        "seleccion/candidaturas/<int:pk>/",
        views.candidatura_detail,
        name="candidatura_detail",
    ),
    path(
        "seleccion/candidaturas/<int:pk>/editar/",
        views.candidatura_edit,
        name="candidatura_edit",
    ),
    path(
        "seleccion/candidaturas/<int:pk>/seguimiento/",
        views.candidatura_seguimiento_add,
        name="candidatura_seguimiento_add",
    ),
    path(
        "seleccion/candidaturas/<int:pk>/cv/",
        views.candidatura_cv,
        name="candidatura_cv",
    ),
]

# RRHH_CV_OCR_V1
urlpatterns += [
    path(
        "seleccion/procesos/<int:proceso_pk>/candidatura-desde-cv/",
        views.candidatura_desde_cv,
        name="candidatura_desde_cv",
    ),
]
# RRHH_CV_PDF_VIEWER_V1_2
urlpatterns += [
    path(
        "seleccion/procesos/<int:proceso_pk>/"
        "candidatura-desde-cv/preview/",
        views.candidatura_cv_preview,
        name="candidatura_cv_preview",
    ),
]

# RRHH_CV_FAST_LOAD_DUPLICATE_DELETE_V1
urlpatterns += [
    path(
        "seleccion/candidaturas/<int:pk>/quitar-curriculo/",
        views.candidatura_cv_remove,
        name="candidatura_cv_remove",
    ),
    path(
        "seleccion/candidaturas/<int:pk>/eliminar/",
        views.candidatura_delete,
        name="candidatura_delete",
    ),
]
# RRHH_FILTERED_PRINT_V1
urlpatterns += [
    path(
        "seleccion/imprimir/",
        views.seleccion_personal_print,
        name="seleccion_personal_print",
    ),
]
