from django.urls import path
from . import views

app_name = 'portal'

urlpatterns = [
    path('', views.app_home, name='home'),  # Esto manejará /app/
    # Puedes añadir más rutas aquí
]