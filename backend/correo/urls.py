from django.urls import path

from . import views


app_name = "correo"


urlpatterns = [
    path(
        "",
        views.inicio,
        name="inicio",
    ),
    path(
        "contador-flotante/",
        views.contador_flotante,
        name="contador_flotante",
    ),
    path(
        "enviar/",
        views.enviar_mensaje,
        name="enviar_mensaje",
    ),
    path(
        "archivos/carpetas/",
        views.carpetas_archivos,
        name="carpetas_archivos",
    ),
    path(
        (
            "mensaje/<int:uid>/adjunto/"
            "<int:indice>/descargar/"
        ),
        views.descargar_adjunto,
        name="descargar_adjunto",
    ),
    path(
        (
            "mensaje/<int:uid>/adjunto/"
            "<int:indice>/guardar/"
        ),
        views.guardar_adjunto_archivos,
        name="guardar_adjunto_archivos",
    ),
    path(
        "mensaje/<int:uid>/",
        views.detalle_mensaje,
        name="detalle_mensaje",
    ),
    path(
        "mensaje/<int:uid>/estado/",
        views.estado_mensaje,
        name="estado_mensaje",
    ),
]
