from django.urls import path
from . import views

app_name = "informes"

urlpatterns = [
    path("", views.informes_index, name="index"),
]
