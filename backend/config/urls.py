
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.views.generic import RedirectView

# Health inline para no depender de otros módulos
def health(request):
    return HttpResponse("ok")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", lambda r: HttpResponse("OK")),
    # raíz → tabs
    path("", RedirectView.as_view(url="/manual/tabs/", permanent=False)),
    # frontend (tabs)
    path("manual/", include("apps.frontend.urls")),
    # planificación + gantt
    path("manual/", include("apps.core.ui_urls")),
]
