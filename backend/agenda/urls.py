from django.urls import path
from .views import AgendaView, EventoCreateView, EventoUpdateView

app_name = "agenda"

urlpatterns = [
    path("", AgendaView.as_view(), name="home"),
    path("nuevo/", EventoCreateView.as_view(), name="create"),
    path("<int:pk>/editar/", EventoUpdateView.as_view(), name="update"),
]
