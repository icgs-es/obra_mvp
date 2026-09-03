from django.urls import path

from . import views


app_name = "ayuda"


urlpatterns = [
    path(
        "",
        views.centro,
        name="centro",
    ),
    path(
        "api/buscar/",
        views.buscar_api,
        name="buscar_api",
    ),
    # AYUDA_ARTICLE_PANEL_API_V1
    path(
        "api/articulo/<path:article_id>/",
        views.articulo_api,
        name="articulo_api",
    ),
    path(
        "articulo/<path:article_id>/",
        views.articulo,
        name="articulo",
    ),
]
