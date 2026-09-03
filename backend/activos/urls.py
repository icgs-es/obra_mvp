# activos/urls.py

from django.urls import path
from . import views

app_name = "activos"

urlpatterns = [

    # 📋 Listado operativo de activos
    path("", views.activo_list, name="list"),

    # # ➕ Crear activo
    path("nuevo/", views.activo_create, name="create"),

    # # 👁 Detalle
    path("<int:pk>/", views.activo_detail, name="detail"),

    # # ✏️ Editar
    path("<int:pk>/editar/", views.activo_update, name="update"),

    # # 🗑 Eliminar
    path("<int:pk>/eliminar/", views.activo_delete, name="delete"),

]