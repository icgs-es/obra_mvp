from django.contrib import admin
from django.urls import path, include
from django.views.generic.base import RedirectView
from django.http import HttpResponse

def health(request):
    return HttpResponse("ok", content_type="text/plain")

urlpatterns = [
    path("app/informes/", include(("informes.urls", "informes"), namespace="informes")),
    # COMPARATIVAS_PRESUPUESTOS_URL_V1
    path("app/gestion/comparativas/", include("comparativas.urls")),
    path("app/gestion/", include(("apps.gestion.urls", "gestion"), namespace="gestion")),
    # Health
    path("health", health, name="health"),

    # Legacy CRM redirects
    path("crm/", RedirectView.as_view(url="/app/crm/", permanent=False)),
    path("crm/leads/", RedirectView.as_view(url="/app/crm/leads/", permanent=False)),

    # Auth
    path("accounts/", include("django.contrib.auth.urls")),

    path(
        "app/ayuda/",
        include(
            ("ayuda.urls", "ayuda"),
            namespace="ayuda",
        ),
    ),

    # INTASA IA V1A
    path("app/ia/", include(("intasa_ia.urls", "intasa_ia"), namespace="intasa_ia")),

    # Correo corporativo
    path("app/correo/", include(("correo.urls", "correo"), namespace="correo")),

    # Portal (Mi jornada) bajo /app/
    path("app/", include(("portal.urls", "portal"), namespace="portal")),

    # Planificación de Obra
    path("app/obra-movil/", include(("obra_movil.urls", "obra_movil"), namespace="obra_movil")),
    path("app/planificacion-obra/", include(("planificacion_obra.urls", "planificacion_obra"), namespace="planificacion_obra")),

    # Tareas y Agenda
    path("app/tareas/", include(("tareas.urls", "tareas"), namespace="tareas")),
    path("app/agenda/", include(("agenda.urls", "agenda"), namespace="agenda")),

    # FICHAJES / MI JORNADA
    path("app/fichajes/", include(("fichajes.urls", "fichajes"), namespace="fichajes")),
    path("app/rrhh/", include(("rrhh.urls", "rrhh"), namespace="rrhh")),
    
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