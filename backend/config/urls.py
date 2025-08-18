
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse

# Health inline para no depender de otros módulos
def health(request):
    return HttpResponse("ok")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health, name="health"),
    path("manual/", include("apps.frontend.urls")),  # Tabs SAFE
]
