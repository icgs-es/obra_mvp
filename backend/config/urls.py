from django.contrib import admin
from django.urls import path, include
from django.views.generic.base import RedirectView
from django.http import HttpResponse

def health(request):
    return HttpResponse("ok", content_type="text/plain")

urlpatterns = [
    # Health
    path("health", health, name="health"),

    # Legacy CRM redirects
    path("crm/", RedirectView.as_view(url="/app/crm/", permanent=False)),
    path("crm/leads/", RedirectView.as_view(url="/app/crm/leads/", permanent=False)),

    # Auth
    path("accounts/", include("django.contrib.auth.urls")),

    # Portal (Mi jornada) bajo /app/
    path("app/", include(("portal.urls", "portal"), namespace="portal")),

    # Tareas y Agenda
    path("app/tareas/", include(("tareas.urls", "tareas"), namespace="tareas")),
    path("app/agenda/", include(("agenda.urls", "agenda"), namespace="agenda")),

    # FICHAJES / MI JORNADA
    path("app/fichajes/", include(("fichajes.urls", "fichajes"), namespace="fichajes")),
    
    # --- CONSTRUCTORA (usa tu app core)
    path("manual/", include(("apps.core.ui_urls", "core_ui"), namespace="construccion")),

    # CRM
    path("app/crm/", include("crm.urls")),
    
    # Admin
    path("admin/", admin.site.urls),
    
    path("app/archivos/", include("archivos.urls", namespace="archivos")),
    
    path("", RedirectView.as_view(url="/app/", permanent=False), name="root"),

    # Activos
    path("activos/", include(("activos.urls", "activos"), namespace="activos")),
]