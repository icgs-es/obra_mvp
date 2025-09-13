from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.views.generic import TemplateView
from django.contrib.auth import views as auth_views

def health(request):
    return HttpResponse("OK")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health),
    
    # URLs de autenticación CRÍTICAS (añade esto)
    path("accounts/login/", auth_views.LoginView.as_view(
        template_name='registration/login.html',
        redirect_authenticated_user=True
    ), name='login'),
    
    path("accounts/logout/", auth_views.LogoutView.as_view(
        next_page='/'
    ), name='logout'),
    
    # HOME pública → homes.html (tu portada buena)
    path("", TemplateView.as_view(template_name="homes.html"), name="home"),

    # Redirección raíz
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    
    # Tus apps existentes
    path("manual/", include("apps.frontend.urls")),
    path("manual/", include("apps.core.ui_urls")),
    
    # Nuevas apps
    path("app/", include("portal.urls", namespace="portal")),
    path("app/tareas/", include("tareas.urls", namespace="tareas")),
    path("app/agenda/", include("agenda.urls", namespace="agenda")),
    path("app/usuarios/", include("usuarios.urls", namespace="usuarios")),
    path("accounts/", include("django.contrib.auth.urls")),  # login, logout, password_change...
    path("app/", include(("portal.urls", "portal"), namespace="portal")),  # ✅ una sola vez
    
    # Diagnostico
    path('diagnostico-error/', TemplateView.as_view(template_name='diagnostico-error.html'), name='diagnostico'),
    # Ruta temporal para diagnóstico
    path('diagnostico-templates/', TemplateView.as_view(template_name='diagnostico-templates.html')),
   
]