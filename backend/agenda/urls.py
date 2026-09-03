from django.urls import path
from . import views

app_name = "agenda"

urlpatterns = [
    # UI
    path("", views.calendar_view, name="home"),
    path("nuevo/", views.create_view, name="create"),
    path("<int:pk>/editar/", views.update_view, name="edit"),

    # API FullCalendar
    path("api/calendars/", views.api_calendars, name="api_calendars"),
    path("api/events/", views.api_events, name="api_events"),
    path("api/events/<int:pk>/", views.api_event_detail, name="api_event_detail"),
    path("api/events/<int:pk>/action/", views.event_action, name="event_action"),

    # Import / Export
    path("importar/", views.import_view, name="import"),
    path("exportar/", views.export_view, name="export"),
    path("feed/<str:token>.ics", views.ics_feed, name="ics_feed"),
]
