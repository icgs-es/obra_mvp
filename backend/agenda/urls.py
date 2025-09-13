from django.urls import path
from . import views
from .views import AgendaView, EventoCreateView, EventoUpdateView

app_name = "agenda"

urlpatterns = [
    path("", AgendaView.as_view(), name="home"),
    path("nuevo/", EventoCreateView.as_view(), name="create"),
    path("<int:pk>/editar/", EventoUpdateView.as_view(), name="update"),

    # Calendario principal
    path("", views.calendar_view, name="list"),

    # API para FullCalendar
    path("api/calendars/", views.api_calendars, name="api_calendars"),
    path("api/events/", views.api_events, name="api_events"),

    path("nuevo/", views.EventoCreateView.as_view(), name="create"),
    path("<int:pk>/editar/", views.EventoUpdateView.as_view(), name="update"),
]
