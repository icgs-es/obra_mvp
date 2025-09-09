from django.urls import path
from .views import UsuarioListView, UsuarioCreateView, UsuarioUpdateView, UsuarioDeactivateView

app_name = "usuarios"

urlpatterns = [
    path("", UsuarioListView.as_view(), name="list"),
    path("nuevo/", UsuarioCreateView.as_view(), name="create"),
    path("<int:pk>/editar/", UsuarioUpdateView.as_view(), name="update"),
    path("<int:pk>/baja/", UsuarioDeactivateView.as_view(), name="deactivate"),
]
