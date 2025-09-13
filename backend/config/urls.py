from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [
    # Home pública (puede ser tu homes.html)
    path("", TemplateView.as_view(template_name="homes.html"), name="home"),

    # Auth
    path("accounts/", include("django.contrib.auth.urls")),

    # Portal (Mi jornada) bajo /app/
    path("app/", include(("portal.urls", "portal"), namespace="portal")),

    # Tareas y Agenda
    path("app/tareas/", include(("tareas.urls", "tareas"), namespace="tareas")),
    path("app/agenda/", include(("agenda.urls", "agenda"), namespace="agenda")),

    # --- CONSTRUCTORA (usa tu app core)
    path("manual/", include(("apps.core.ui_urls", "core_ui"), namespace="construccion")),

    # Admin
    path("admin/", admin.site.urls),
]