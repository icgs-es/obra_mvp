
from django.urls import path
from . import views

urlpatterns = [
    path("tabs/ping/", views.ping, name="tabs_ping"),
    path("tabs/", views.tabs_home, name="tabs_home"),
    path("tabs/obras/", views.tab_obras, name="tab_obras"),
    path("tabs/obras/<int:pk>/row/", views.obra_row, name="obra_row"),
    path("tabs/obras/<int:pk>/edit/", views.obra_edit, name="obra_edit"),
    path("tabs/obras/<int:pk>/delete/", views.obra_delete, name="obra_delete"),

    path("tabs/subobras/", views.tab_subobras, name="tab_subobras"),
    path("tabs/subobras/<int:pk>/row/", views.subobra_row, name="subobra_row"),
    path("tabs/subobras/<int:pk>/edit/", views.subobra_edit, name="subobra_edit"),
    path("tabs/subobras/<int:pk>/delete/", views.subobra_delete, name="subobra_delete"),

    path("tabs/capitulos/", views.tab_capitulos, name="tab_capitulos"),
    path("tabs/capitulos/<int:pk>/row/", views.capitulo_row, name="capitulo_row"),
    path("tabs/capitulos/<int:pk>/edit/", views.capitulo_edit, name="capitulo_edit"),
    path("tabs/capitulos/<int:pk>/delete/", views.capitulo_delete, name="capitulo_delete"),

    path("tabs/partidas/", views.tab_partidas, name="tab_partidas"),
    path("tabs/partidas/<int:pk>/row/", views.partida_row, name="partida_row"),
    path("tabs/partidas/<int:pk>/edit/", views.partida_edit, name="partida_edit"),
    path("tabs/partidas/<int:pk>/delete/", views.partida_delete, name="partida_delete"),
]
