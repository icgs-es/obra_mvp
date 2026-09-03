from django.urls import path

from . import views


app_name = "intasa_ia"


urlpatterns = [
    path(
        "<int:pk>/mensajes/<int:message_id>/estado/",
        views.estado_procesamiento,
        name="estado_procesamiento",
    ),
    path(
        "<int:pk>/mensajes/<int:message_id>/reintentar/",
        views.reintentar_procesamiento,
        name="reintentar_procesamiento",
    ),
    path(
        "adjuntos/<uuid:attachment_id>/descargar/",
        views.descargar_adjunto,
        name="descargar_adjunto",
    ),
    path(
        "",
        views.inicio,
        name="inicio",
    ),
    path(
        "<int:pk>/compartir/",
        views.compartir,
        name="compartir",
    ),
    path(
        "<int:pk>/compartir/<int:user_id>/retirar/",
        views.retirar_compartido,
        name="retirar_compartido",
    ),
    path(
        "<int:pk>/eliminar/",
        views.eliminar_conversacion,
        name="eliminar_conversacion",
    ),
    path(
        "<int:pk>/",
        views.inicio,
        name="detalle",
    ),
]
